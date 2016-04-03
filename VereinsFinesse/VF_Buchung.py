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

    def __init__(self):
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

        # Die Buchung auf der anderen Seite, von der diese importiert wurde
        self.original_buchung = None
        # Buchungen auf der anderen Seite, die von dieser kopiert wurden (mehrere bei Stornos im VF)
        self.kopierte_buchungen = None

        self.fehler_beschreibung = None

    def init_from_vf(self, value_dict, steuer_configuration):
        """
        :param value_dict: Dict
        :param steuer_configuration: SteuerConfiguration
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
            self.steuerfall = steuer_configuration.steuerfall_for_vf_steuerkonto_and_steuersatz(steuer_konto, steuer_satz)
            if not self.steuerfall:
                self.fehler_beschreibung = u'Kombination aus Steuerkonto ({0}) und Steuersatz ({1}) unbekannt'.format(steuer_konto, steuer_satz)
                return False

            # Der Steuersatz aus dem Vereinsflieger muss zum Steuerkonto passen.
            if steuer_satz != self.steuerfall.ust_satz:
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

    def finesse_buchung_from_vf_buchung(self):
        """
        :rtype: Finesse_Buchung
        """
        assert self.vf_belegart != vf_belegart_for_import_from_finesse

        # Kontozuordnung bestimmen.
        if self.kopierte_buchungen:
            eine_finesse_buchung = self.kopierte_buchungen[0]
            konto_im_haben = self.konto == eine_finesse_buchung.konto_haben
            assert konto_im_haben or self.konto == eine_finesse_buchung.konto_soll
        else:
            konto_im_haben = self.betrag >= Decimal(0)

        # Initialisieren einer Finesse-Buchung mit den Werten der VF-Buchung.
        result = Finesse_Buchung.Finesse_Buchung()

        if konto_im_haben:
            result.konto_haben = self.konto
            # result.konto_haben_kostenstelle = self.konto_kostenstelle
            result.konto_soll = self.gegen_konto
            # result.konto_soll_kostenstelle = self.gegen_konto_kostenstelle
            result.betrag_haben = self.betrag
            result.betrag_soll = result.betrag_haben
            if self.has_steuer:
                result.steuer_konto = self.steuer_konto # TODO: map to correct Konto
                result.betrag_soll = round_to_two_places(result.betrag_haben / (Decimal(1) + self.mwst_satz / Decimal(100)))
                result.steuer_betrag_soll = result.betrag_haben - result.betrag_soll
                result.steuer_betrag_haben = Decimal(0)
        else:
            result.konto_soll = self.konto
            # result.konto_soll_kostenstelle = self.konto_kostenstelle
            result.konto_haben = self.gegen_konto
            # result.konto_haben_kostenstelle = self.gegen_konto_kostenstelle
            result.betrag_soll = -self.betrag
            result.betrag_haben = result.betrag_soll
            if self.has_steuer:
                result.steuer_konto = self.steuer_konto # TODO: map to correct Konto
                result.betrag_haben = round_to_two_places(result.betrag_soll / (Decimal(1) + self.mwst_satz / Decimal(100)))
                result.steuer_betrag_haben = result.betrag_soll - result.betrag_haben
                result.steuer_betrag_soll = Decimal(0)

        # Wenn es bereits Buchungen in Finesse zu dieser Buchung gibt, wird der Saldo für die neue Buchung gebildet.
        if self.kopierte_buchungen:
            for iBuchung in self.kopierte_buchungen:
                assert iBuchung.matches_konten_of_buchung(result)
                result.betrag_soll -= iBuchung.betrag_soll
                result.betrag_haben -= iBuchung.betrag_haben
                if self.has_steuer:
                    result.steuer_betrag_soll -= iBuchung.steuer_betrag_soll
                    result.steuer_betrag_haben -= iBuchung.steuer_betrag_haben

        # Finesse protestiert bei Buchung mit Betrag 0, was irgendwie verständlich ist.
        if result.betrag_soll == Decimal(0) and result.betrag_haben == Decimal(0):
            return None

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
