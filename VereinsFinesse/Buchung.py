# -*- coding: utf-8 -*-

import string
import copy
import re
import math
from decimal import *
from Configuration import *
import CheckDigit

finesse_journal_for_import_from_vf = u'Vereinsflieger-Import'
finesse_fournal_for_export_to_vf = u'Dialog'
vf_belegart_for_import_from_finesse = u'FD'

getcontext().rounding = ROUND_HALF_UP

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

class Buchung:
    """Räpresentiert eine Buchung im Vereinsflieger oder Finesse"""

    def __init__(self):
        self.vf_nr = None
        self.finesse_buchungs_journal = None
        self.finesse_journalnummer = None
        self.finesse_beleg2 = None
        self.finesse_steuercode = None
        self.kostenstelle = None
        self.vf_belegart = None
        self.vf_belegnummer = None
        self.datum = None
        self.buchungstext = None
        self.konto_soll = None
        self.konto_soll_kostenstelle = None
        self.konto_soll_name = None
        self.konto_haben = None
        self.konto_haben_kostenstelle = None
        self.konto_haben_name = None
        self.steuer_konto = None
        self.steuer_konto_name = None
        self.betrag_soll = None
        self.betrag_haben = None
        self.steuer_betrag_soll = None
        self.steuer_betrag_haben = None
        self.mwst_satz = None
        self.rechnungsnummer = None

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
        # TODO: soll Abrechnungsnr wirklich auf Rechnungsnummer abgebildet werden?
        # Ja: so werden in Finesse für eine Mitgliederrechnung Splitbuchungen erzeugt.
        self.rechnungsnummer = value_dict[u'Abrechnungsnr']   # Die Rechnungs"nummer" kann beliebiger Text sein
        betrag = decimal_with_decimalcomma(value_dict[u'Betrag'])

        steuer_satz = Decimal(0)
        steuer_satz_text = value_dict[u'MwSt(%)']
        steuer_konto_text = value_dict[u'S-Konto']
        if len(steuer_konto_text) > 0:
            steuer_konto = int(steuer_konto_text)
            steuer_satz = Decimal(steuer_satz_text)
            steuerfall = steuer_configuration.steuerfall_for_vf_steuerkonto_and_steuersatz(steuer_konto, steuer_satz)
            if not steuerfall:
                self.fehler_beschreibung = u'Kombination aus Steuerkonto ({0}) und Steuersatz ({1}) unbekannt'.format(steuer_konto, steuer_satz)
                return False

            # Der Steuersatz aus dem Vereinsflieger muss zum Steuerkonto passen.
            if steuer_satz != steuerfall.ust_satz:
                self.fehler_beschreibung = (u'MwSt-Satz ({0}) aus Vereinsflieger passt nicht zum dem des Steuerkontos ({1})'
                                            .format(steuer_satz, steuerfall.ust_satz))
                return False
            self.steuer_konto = steuer_konto
            self.mwst_satz = steuer_satz
            self.finesse_steuercode = steuerfall.code
        else:
            # Kein Steuerkonto angegeben, dann muss der MwSt-Satz 0 sein (oder leer).
            if len(steuer_satz_text) > 0 and int(steuer_satz_text) != 0:
                self.fehler_beschreibung = u'MwSt-Satz > 0 ({0}) ohne Steuerkonto'.format(steuer_satz_text)
                return False

        # Im Buchungsexport des VF entspricht 'Konto' stets dem Habenkonto für Finesse und 'Gegenkonto' dem
        # Sollkonto.
        # Achtung: Dies gilt nicht im Buchungsjournal-View im VF. Wenn dort 'Betrag(K)' negativ ist, werden die
        # Konten für den Export vertauscht.
        (self.konto_haben, self.konto_haben_kostenstelle) = vf_read_konto(value_dict[u'Konto'])
        (self.konto_soll, self.konto_soll_kostenstelle) = vf_read_konto(value_dict[u'G-Konto'])
        self.betrag_soll = betrag
        self.betrag_haben = betrag
        if steuer_satz > Decimal(0):
            self.betrag_haben = round_to_two_places(betrag / (Decimal(1) + steuer_satz / Decimal(100)))
            # Auf welche Seite des Steuerkontos die Steuer gebucht wird, hängt davon ab, ob es ein Vorsteuer- oder
            # ein Umsatzsteuerkonto ist. Dies ist im Steuerfall mit geschlüsselt.
            if steuerfall.steuer_ins_haben:
                self.steuer_betrag_haben = self.betrag_soll - self.betrag_haben
                self.steuer_betrag_soll = Decimal(0)
            else:
                self.steuer_betrag_soll = self.betrag_soll - self.betrag_haben
                self.steuer_betrag_haben = Decimal(0)

        if self.konto_haben_kostenstelle:
            self.kostenstelle = self.konto_haben_kostenstelle
        elif self.konto_soll_kostenstelle:
            self.kostenstelle = self.konto_soll_kostenstelle

        # Plausibilitätschecks:
        if self.konto_haben_kostenstelle and self.konto_soll_kostenstelle:
            self.fehler_beschreibung = u'Beide Konten haben eine Kostenstelle'
            return False

        return True

    def init_from_finesse(self, value_dict, steuer_configuration):
        assert self.datum is None  # the instance must be empty so far

        self.source_values = value_dict

        journal_name = value_dict[u'Buchungs-Journal']
        self.finesse_buchungs_journal = journal_name
        self.finesse_journalnummer = int(value_dict[u'Journalnummer'])
        # Feststellen, ob diese Buchung ursprünglich vom VF importiert wurde.
        beleg2_text = value_dict[u'Beleg 2']
        # Anfang 2016 haben einige Buchungen in Finesse kleine Zahlen in Beleg 2 bekommen
        # Daher Heuristik, um 6-stellige VF-Buchungsnummern zu erkennen.
        if len(beleg2_text) >= 6:
            vf_nr_text = CheckDigit.check_and_strip_checkdigit(beleg2_text)
            if not vf_nr_text:
                self.fehler_beschreibung = u'Falsche Prüfziffer für VF-Nr in Belegnummer 2({0})'.format(beleg2_text)
                return False
            self.vf_nr = int(vf_nr_text)

        self.datum = value_dict[u'Belegdatum']
        self.buchungstext = value_dict[u'Buchungs-Text']
        self.konto_soll = int(value_dict[u'Konto Soll'])
        self.konto_soll_name = value_dict[u'Bezeichnung Konto Soll']
        self.konto_haben = int(value_dict[u'Konto Haben'])
        self.konto_haben_name = value_dict[u'Bezeichnung Konto Haben']

        # Finesse exportiert '0' für 'kein Konto'
        steuer_konto = int(value_dict[u'Steuerkonto'])

        steuercode_text = value_dict[u'Steuercode']
        if len(steuercode_text) > 0:
            steuercode = int(steuercode_text)
            steuerfall = steuer_configuration.steuerfall_for_finesse_steuercode(steuercode)
            if not steuerfall:
                self.fehler_beschreibung = u'Unbekannter Steuercode ({0})'.format(steuercode)
                return False

            # Das Steuerkonto aus Finesse muss zum Steuercode passen.
            if steuer_konto != steuerfall.konto_finesse:
                self.fehler_beschreibung = (u'Steuerkonto ({0}) aus Finesse passt nicht zum Steuercode ({1})'
                                            .format(steuer_konto, steuercode))
                return False
            self.steuer_konto = steuer_konto
            self.steuer_konto_name = value_dict[u'Bezeichnung Steuerkonto']
            self.steuer_betrag_soll = decimal_with_decimalcomma(value_dict[u'Steuerbetrag Soll'])
            self.steuer_betrag_haben = decimal_with_decimalcomma(value_dict[u'Steuerbetrag Haben'])
            self.mwst_satz = steuerfall.ust_satz
            self.finesse_steuercode = steuercode
        else:
            # Kein Steuercode angegeben, dann müssen das übrige Steuerzeugs leer oder 0 sein.
            if (   steuer_konto != 0
                or decimal_with_decimalcomma(value_dict[u'Steuerbetrag Soll']) != Decimal(0)
                or decimal_with_decimalcomma(value_dict[u'Steuerbetrag Haben']) != Decimal(0)):
                self.fehler_beschreibung = u'Kein Steuercode, aber andere Steuerangaben sind nicht alle 0'
                return False

        self.betrag_soll = decimal_with_decimalcomma(value_dict[u'Betrag Soll'])
        self.betrag_haben = decimal_with_decimalcomma(value_dict[u'Betrag Haben'])
        self.rechnungsnummer = value_dict[u'Rechnungsnummer']   # Die Rechnungs"nummer" kann beliebiger Text sein

        # Finesse schreibt "000000000" für leere Kostenstellen.
        self.kostenstelle = int(value_dict[u'Kostenrechnung 1'])
        if self.kostenstelle == 0:
            self.kostenstelle = None

        return True

    def create_placeholder_for_deleted_vf_buchung(self):
        # Start with a copy of self and update as necessary
        result = copy.copy(self)
        result.finesse_buchungs_journal = None
        result.finesse_journalnummer = None
        result.finesse_beleg2 = None
        result.betrag_soll = Decimal(0)
        result.betrag_haben = Decimal(0)
        result.steuer_betrag_soll = Decimal(0)
        result.steuer_betrag_haben = Decimal(0)
        result.original_buchung = None
        result.kopierte_buchungen = None
        return result

    def finesse_buchung_from_vf_buchung(self):
        """
        :rtype: Buchung
        """
        # Wenn die Buchung bisher ganz fehlt in Finesse, wird sie ungeändert übertragen
        if not self.kopierte_buchungen:
            # Finesse protestiert bei Buchung mit Betrag 0, was irgendwie verständlich ist.
            if self.betrag_soll == Decimal(0):
                return None
            return self

        # Saldo aus den bisher nach Finesse übertragenen Buchungen bilden.
        betrag_soll = self.betrag_soll
        betrag_haben = self.betrag_haben
        steuer_betrag_soll = self.steuer_betrag_soll
        steuer_betrag_haben = self.steuer_betrag_haben

        for iBuchung in self.kopierte_buchungen:
            assert iBuchung.matches_konten_of_buchung(self)
            betrag_soll -= iBuchung.betrag_soll
            betrag_haben -= iBuchung.betrag_haben
            if iBuchung.has_steuer:
                steuer_betrag_soll -= iBuchung.steuer_betrag_soll
                steuer_betrag_haben -= iBuchung.steuer_betrag_haben

        if betrag_soll == Decimal(0) and betrag_haben == Decimal(0):
            return None

        # Start with a copy of self and update the amounts
        result = copy.copy(self)
        result.betrag_soll = betrag_soll
        result.betrag_haben = betrag_haben
        result.steuer_betrag_soll = steuer_betrag_soll
        result.steuer_betrag_haben = steuer_betrag_haben
        return result

    def prepare_for_vf(self, konten_mit_kostenstelle):
        """
        :rtype: bool
        """
        # Kostenstelle einem Konto zuordnen:
        if self.kostenstelle:
            if self.konto_haben_kostenstelle:
                assert self.konto_haben_kostenstelle == self.kostenstelle
            elif self.konto_soll_kostenstelle:
                assert self.konto_soll_kostenstelle == self.kostenstelle
            else:
                if konten_mit_kostenstelle.enthaelt_konto(self.konto_soll):
                    if konten_mit_kostenstelle.enthaelt_konto(self.konto_haben):
                        self.fehler_beschreibung = u'Buchung von Erfolgskonto zu Erfolgskonto, keine Zuordnung der Kostenstelle für Export zu VF möglich'
                        return False
                    self.konto_soll_kostenstelle = self.kostenstelle
                elif konten_mit_kostenstelle.enthaelt_konto(self.konto_haben):
                    self.konto_haben_kostenstelle = self.kostenstelle
                else:
                    self.fehler_beschreibung = u'Kostenstelle kann für Export zu VF keinem der Konten zugeordnet werden'
                    return False
        return True

    @property
    def has_steuer(self):
        """
        :rtype: bool
        """
        return self.steuer_konto != None

    def matches_buchung(self, other_buchung):
        """
        :type other_buchung: Buchung
        :param other_buchung: Buchung
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
        :param other_buchung:Buchung
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
        assert self.finesse_buchungs_journal == finesse_fournal_for_export_to_vf
        # Note: fehlende Dict-Einträge werden automatisch als Leerstrings exportiert.
        result = {}
        result[u'Datum'] = self.datum
        result[u'Konto'] = vf_format_konto(self.konto_haben, self.konto_haben_kostenstelle)
        result[u'Betrag'] = self.betrag_soll
        result[u'Gegenkonto'] = vf_format_konto(self.konto_soll, self.konto_soll_kostenstelle)
        if self.has_steuer:
            result[u'Steuerkonto'] = self.steuer_konto
            result[u'Mwst'] = self.mwst_satz
        result[u'Buchungstext'] = self.buchungstext
        result[u'BelegArt'] = 'FD'
        result[u'BelegNr'] = CheckDigit.append_checkdigit(unicode(self.finesse_journalnummer))
        return result

    @classmethod
    def fieldnames_for_export_to_finesse(cls):
        return [u'Datum',u'Buchungstext',u'Betrag',u'USt-Code',u'Betrag USt',u'Konto Haben',u'Konto Soll',u'Kostenrechnungsobjekt 1',u'Rechnungsnummer',u'Belegnummer 1',u'VF_Nr']

    @property
    def dict_for_export_to_finesse(self):
        """
        :rtype: dict
        """
        assert self.vf_belegart != vf_belegart_for_import_from_finesse
        # Note: fehlende Dict-Einträge werden automatisch als Leerstrings exportiert.
        result = {}
        result[u'Datum'] = self.datum
        result[u'Buchungstext'] = self.buchungstext
        result[u'Betrag'] = self.betrag_soll
        if self.has_steuer and self.finesse_steuercode != 1:
            result[u'USt-Code'] = self.finesse_steuercode
            if self.steuer_betrag_haben:
                result[u'Betrag USt'] = self.steuer_betrag_haben
            else:   # passiert für Steuercode 1 (Umsatzsteuerfrei)
                result[u'Betrag USt'] = Decimal(0)
        result[u'Konto Haben'] = self.konto_haben
        result[u'Konto Soll'] = self.konto_soll
        if self.kostenstelle:
            result[u'Kostenrechnungsobjekt 1'] = self.kostenstelle
        if self.rechnungsnummer:
            result[u'Rechnungsnummer'] = self.rechnungsnummer
        if self.vf_belegnummer:
            result[u'Belegnummer 1'] = self.vf_belegnummer
        result[u'VF_Nr'] = CheckDigit.append_checkdigit(unicode(self.vf_nr))
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
