# -*- coding: utf-8 -*-

import string
import copy
import re
import math
import decimal
from decimal import Decimal
import Configuration
import CheckDigit
import Finesse_Buchung

vf_belegart_for_import_from_finesse = u'FD'

decimal.getcontext().rounding = decimal.ROUND_HALF_UP

vf_konto_und_kostenstelle_expr = re.compile('\s*([0-9]{4})-([0-9]{3})\s*$')


def decimal_with_decimalcomma(s):
    """
    :param s:String
    :rtype: Decimal
    """
    s = string.replace(s, '.', '')
    return Decimal(string.replace(s, ',', '.', 1))


def round_to_two_places(d):
    """
    :param d:Decimal
    :rtype: Decimal
    """
    TWOPLACES = Decimal(10) ** -2  # same as Decimal('0.01')
    return d.quantize(TWOPLACES)

class VF_Buchung:
    """Räpresentiert eine Buchung im Vereinsflieger"""

    def __init__(self, konfiguration):
        """
        :param konfiguration: Configuration.Konfiguration
        """
        assert konfiguration
        self.konfiguration = konfiguration
        self.vf_nr = None
        self.datum = None
        self.konto = None
        self.konto_kostenstelle = None
        self.gegen_konto = None
        self.gegen_konto_kostenstelle = None
        self.betrag = None
        self.steuer_konto = None
        self.mwst_satz = None
        self.buchungstext = None
        self.vf_belegart = None
        self.vf_belegnummer = None
        self.abrechnungsnr = None
        self.steuerfall = None

        self.finesse_journalnummer = None

        # Die Finess-Buchung, von der dieser bei einem früheren Abgleich importiert wurde.
        self.original_finesse_buchung = None
        # Finesse-Buchungen, die von dieser bei früheren Abgleichen kopiert wurden (mehrere bei Stornos im VF).
        self.kopierte_finesse_buchungen = None

        self.fehler_beschreibung = None

    def init_from_vf(self, value_dict):
        """
        :param value_dict: Dict
        :rtype: bool
        """
        assert self.datum is None  # the instance must be empty so far

        # Die Quellwerte werden für den Fall einer Fehlerausgabe gemerkt.
        self.source_values = value_dict

        self.vf_nr = int(value_dict[u'Nr'])
        self.vf_belegart = value_dict[u'Belegart']
        belegnummer_text = value_dict[u'Belegnummer']
        # Feststellen, ob diese Buchung ursprünglich von Finesse importiert wurde.
        if self.vf_belegart == vf_belegart_for_import_from_finesse:
            finesse_journal_nummer_text = CheckDigit.check_and_strip_checkdigit(belegnummer_text)
            if not finesse_journal_nummer_text:
                self.fehler_beschreibung = u'Falsche Prüfziffer für Finesse Journalnummer in Belegnummer ({0})'.format(belegnummer_text)
                return False
            self.finesse_journalnummer = int(finesse_journal_nummer_text)
        else:
            self.vf_belegnummer = int(belegnummer_text)

        self.datum = value_dict[u'Datum']
        self.buchungstext = value_dict[u'Buchungstext']
        self.abrechnungsnr = value_dict[u'Abrechnungsnr']   # Die Rechnungs"nummer" kann beliebiger Text sein
        self.rechnungsnummer = self.abrechnungsnr   # Die Rechnungs"nummer" kann beliebiger Text sein
        self.betrag = decimal_with_decimalcomma(value_dict[u'Betrag'])

        steuer_satz = Decimal(0)
        steuer_satz_text = value_dict[u'MwSt(%)']
        steuer_konto_text = value_dict[u'S-Konto']
        if len(steuer_konto_text) > 0:
            steuer_konto = int(steuer_konto_text)
            steuer_satz = Decimal(steuer_satz_text)
            self.steuerfall = self.konfiguration.steuer_configuration.steuerfall_for_vf_steuerkonto_and_steuersatz(steuer_konto, steuer_satz)
            if not self.steuerfall:
                self.fehler_beschreibung = u'Kombination aus Steuerkonto ({0}) und Steuersatz ({1}) unbekannt'.format(steuer_konto, steuer_satz)
                return False

            # Der Steuersatz aus dem Vereinsflieger muss zum Steuerkonto passen.
            if (steuer_satz != self.steuerfall.ust_satz
                and not (steuer_satz == Decimal(0) and not self.steuerfall.ust_satz)):
                self.fehler_beschreibung = (u'MwSt-Satz ({0}) aus Vereinsflieger passt nicht zum dem des Steuerkontos ({1})'
                                            .format(steuer_satz, self.steuerfall.ust_satz))
                return False
            self.steuer_konto = steuer_konto
            self.mwst_satz = steuer_satz
        else:
            # Kein Steuerkonto angegeben, dann muss der MwSt-Satz 0 sein (oder leer).
            if len(steuer_satz_text) > 0 and int(steuer_satz_text) != 0:
                self.fehler_beschreibung = u'MwSt-Satz > 0 ({0}) ohne Steuerkonto'.format(steuer_satz_text)
                return False

        (self.konto, self.konto_kostenstelle) = vf_read_konto(value_dict[u'Konto'])
        (self.gegen_konto, self.gegen_konto_kostenstelle) = vf_read_konto(value_dict[u'G-Konto'])

        if self.konto_kostenstelle and self.gegen_konto_kostenstelle:
            self.fehler_beschreibung = u'Beide Konten haben eine Kostenstelle'
            return False

        return True

    @property
    def kostenstelle(self):
        kostenstelle = self.konto_kostenstelle
        if not kostenstelle:
            kostenstelle = self.gegen_konto_kostenstelle
        return kostenstelle

    @property
    def is_null(self):
        # Buchungen im VF mit Betrag = 0 sind möglich und entstehen z.B. beim Löschen von Rechnungen.
        # Die Zuordnung der Konten auf Soll und Haben nach dem Vorzeichen ist dann nicht möglich.
        return self.betrag == Decimal(0)

    @property
    def konto_haben(self):
        assert not self.is_null     # der Nullfall ist entartet, Kontenzuordnung ist nicht möglich
        return self.konto if self.betrag > Decimal(0) else self.gegen_konto

    @property
    def konto_soll(self):
        assert not self.is_null     # der Nullfall ist entartet, Kontenzuordnung ist nicht möglich
        return self.gegen_konto if self.betrag > Decimal(0) else self.konto

    def validate_for_original_finesse_buchung(self, original_finesse_buchung):
        if self.is_null:    # muss zuerst gecheckt werden, weil die anderen Checks das voraussetzen
            assert original_finesse_buchung.betrag != Decimal(0)    # Finesse kennt keine Buchungen mit Betrag 0
            return False

        if original_finesse_buchung.steuerfall:
            if not original_finesse_buchung.steuerfall.matches_vf_steuerfall(self.steuerfall):
                return False
        else:
            if self.steuerfall:
                return False

        if (self.konto == original_finesse_buchung.vf_konto
            and self.gegen_konto == original_finesse_buchung.vf_gegen_konto
            and self.betrag == original_finesse_buchung.vf_betrag):
            return True
        # Die ersten Imports in VF haben ohne Steuer die Konten teilweise andersrum geordnet.
        if (not original_finesse_buchung.has_steuer
            and (self.konto == original_finesse_buchung.vf_gegen_konto
                 and self.gegen_konto == original_finesse_buchung.vf_konto
                 and self.betrag == -original_finesse_buchung.vf_betrag)
            ):
            return True
        return False

    def finesse_buchung_from_vf_buchung(self, konten_mit_kostenstelle):
        """
        :rtype: Finesse_Buchung
        """
        assert self.vf_belegart != vf_belegart_for_import_from_finesse

        # Kontozuordnung bestimmen.
        if self.kopierte_finesse_buchungen:
            eine_finesse_buchung = self.kopierte_finesse_buchungen[0]
            konto_im_haben = self.konto == eine_finesse_buchung.konto_haben
            assert konto_im_haben or self.konto == eine_finesse_buchung.konto_soll
        else:
            konto_im_haben = self.betrag >= Decimal(0)

        # Initialisieren einer Finesse-Buchung mit den Werten der VF-Buchung.
        result = Finesse_Buchung.Finesse_Buchung(self.konfiguration)

        # Beträge
        betrag_brutto = self.betrag if konto_im_haben else -self.betrag
        if self.has_steuer:
            result.steuer_konto = self.steuer_konto  # TODO: map to correct Konto
            betrag_netto = round_to_two_places(betrag_brutto / (Decimal(1) + self.mwst_satz / Decimal(100)))
        else:
            betrag_netto = betrag_brutto

        if konto_im_haben:
            result.konto_haben = self.konfiguration.finesse_konto_from_vf_konto(self.konto)
            result.konto_soll = self.konfiguration.finesse_konto_from_vf_konto(self.gegen_konto)
        else:
            result.konto_soll = self.konfiguration.finesse_konto_from_vf_konto(self.konto)
            result.konto_haben = self.konfiguration.finesse_konto_from_vf_konto(self.gegen_konto)

        # Der Nettobetrag geht immer aufs Erfolgskonto.
        if konten_mit_kostenstelle.enthaelt_konto(result.konto_soll):
            if konten_mit_kostenstelle.enthaelt_konto(result.konto_haben):
                self.fehler_beschreibung = u'Buchung mit Steuer von Erfolgskonto auf Erfolgskonto ist nicht sinnvoll'
                return None
            result.betrag_haben = betrag_brutto
            result.steuer_betrag_haben = Decimal(0)
            result.betrag_soll = betrag_netto
            result.steuer_betrag_soll = betrag_brutto - betrag_netto
        elif konten_mit_kostenstelle.enthaelt_konto(result.konto_haben):
            result.betrag_soll = betrag_brutto
            result.steuer_betrag_soll = Decimal(0)
            result.betrag_haben = betrag_netto
            result.steuer_betrag_haben = betrag_brutto - betrag_netto
        elif not self.has_steuer:
            result.betrag_soll = betrag_brutto
            result.steuer_betrag_soll = Decimal(0)
            result.betrag_haben = betrag_brutto
            result.steuer_betrag_haben = Decimal(0)
        else:
            self.fehler_beschreibung = u'Buchungen mit Steuer müssen ein Erfolgskonto benutzen'
            return None

        # Wenn es bereits Buchungen in Finesse zu dieser Buchung gibt, wird der Saldo für die neue Buchung gebildet.
        if self.kopierte_finesse_buchungen:
            for b in self.kopierte_finesse_buchungen:
                if b.matches_konten_of_buchung(result):
                    result.betrag_soll -= b.betrag_soll
                    result.betrag_haben -= b.betrag_haben
                    if self.has_steuer:
                        assert (result.steuer_betrag_soll == Decimal(0)) or (b.steuer_betrag_haben == Decimal(0))
                        assert (result.steuer_betrag_haben == Decimal(0)) or (b.steuer_betrag_soll == Decimal(0))
                        result.steuer_betrag_soll -= b.steuer_betrag_soll
                        result.steuer_betrag_haben -= b.steuer_betrag_haben
                else:
                    assert b.anti_matches_konten_of_buchung(result)
                    result.betrag_soll += b.betrag_haben
                    result.betrag_haben += b.betrag_soll
                    if self.has_steuer:
                        assert (result.steuer_betrag_soll == Decimal(0)) or (b.steuer_betrag_haben == Decimal(0))
                        assert (result.steuer_betrag_haben == Decimal(0)) or (b.steuer_betrag_soll == Decimal(0))
                        result.steuer_betrag_soll += b.steuer_betrag_haben
                        result.steuer_betrag_haben += b.steuer_betrag_soll

        result.vf_nr = self.vf_nr
        result.buchungstext = self.buchungstext
        result.datum = self.datum
        result.steuerfall = self.steuerfall
        if self.steuerfall:
            result.finesse_steuercode = self.steuerfall.code
        # Soll Abrechnungsnr wirklich auf Rechnungsnummer abgebildet werden?
        # Ja: so werden in Finesse für eine Mitgliederrechnung Splitbuchungen erzeugt.
        result.rechnungsnummer = self.abrechnungsnr
        result.vf_belegnummer = self.vf_belegnummer
        result.kostenstelle = self.kostenstelle

        return result

    @property
    def has_steuer(self):
        """
        :rtype: bool
        """
        return self.steuer_konto != None

    def matches_buchung(self, other_buchung):
        """
        :type other_buchung: VF_Buchung
        :param other_buchung: VF_Buchung
        :rtype: bool
        """
        return (self.konto_haben == other_buchung.konto_haben
            and self.konto_soll == other_buchung.konto_soll
            and self.kostenstelle == other_buchung.kostenstelle
            and self.betrag_haben == other_buchung.betrag_haben
            and self.betrag_soll == other_buchung.betrag_soll
            and self.steuer_betrag_haben == other_buchung.steuer_betrag_haben
            and self.steuer_betrag_soll == other_buchung.steuer_betrag_soll)

    def matches_konten_of_buchung(self, other_buchung):
        """
        :param other_buchung:VF_Buchung
        :rtype: bool
        """
        return (self.konto_haben == other_buchung.konto_haben
            and self.konto_soll == other_buchung.konto_soll)

    def anti_matches_konten_of_buchung(self, other_buchung):
        """
        :param other_buchung:VF_Buchung
        :rtype: bool
        """
        return (self.konto_haben == other_buchung.konto_soll
            and self.konto_soll == other_buchung.konto_haben)

    @classmethod
    def fieldnames_for_export_to_vf(cls):
        return [u'Datum',u'Konto',u'Betrag',u'Gegenkonto',u'Steuerkonto',u'Mwst',u'Buchungstext',u'BelegArt',u'BelegNr']

    @property
    def dict_for_export_to_vf(self):
        """
        :rtype: dict
        """
        # Note: fehlende Dict-Einträge werden automatisch als Leerstrings exportiert.
        result = {}
        result[u'Datum'] = self.datum
        result[u'Konto'] = vf_format_konto(self.konto, self.konto_kostenstelle)
        result[u'Betrag'] = self.betrag
        result[u'Gegenkonto'] = vf_format_konto(self.gegen_konto, self.gegen_konto_kostenstelle)
        if self.has_steuer:
            result[u'Steuerkonto'] = self.steuer_konto
            result[u'Mwst'] = self.mwst_satz
        result[u'Buchungstext'] = self.buchungstext
        result[u'BelegArt'] = self.vf_belegart
        result[u'BelegNr'] = self.vf_belegnummer
        return result


def vf_read_konto(dict_value):
    match = vf_konto_und_kostenstelle_expr.match(dict_value)
    if match:
        return(int(match.group(1)), int(match.group(2)))
    else:
        return(int(dict_value), None)

def vf_format_konto(konto, kostenstelle):
    if kostenstelle:
        return u'{0}-{1}'.format (unicode(konto), unicode(kostenstelle))
    else:
        return unicode(konto)
