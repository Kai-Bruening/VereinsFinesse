# -*- coding: utf-8 -*-

import string
import copy
import re
import math
import decimal
from decimal import Decimal
import Configuration
import CheckDigit
import VF_Buchung

finesse_journal_for_import_from_vf = u'Vereinsflieger-Import'
finesse_fournal_for_export_to_vf = u'Dialog'

decimal.getcontext().rounding = decimal.ROUND_HALF_UP


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

class Finesse_Buchung:
    """Räpresentiert eine Buchung in Finesse"""

    def __init__(self):
        self.vf_nr = None
        self.finesse_buchungs_journal = None
        self.finesse_journalnummer = None
        self.finesse_beleg2 = None
        self.finesse_steuercode = None
        self.kostenstelle = None
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
        self.steuerfall = None

        # Die Buchung auf der anderen Seite, von der diese importiert wurde
        self.original_buchung = None
        # Buchungen auf der anderen Seite, die von dieser kopiert wurden (mehrere bei Stornos im VF)
        self.kopierte_buchung = None

        self.fehler_beschreibung = None

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
            self.steuerfall = steuer_configuration.steuerfall_for_finesse_steuercode(steuercode)
            if not self.steuerfall:
                self.fehler_beschreibung = u'Unbekannter Steuercode ({0})'.format(steuercode)
                return False

            # Das Steuerkonto aus Finesse muss zum Steuercode passen.
            if steuer_konto != self.steuerfall.konto_finesse:
                self.fehler_beschreibung = (u'Steuerkonto ({0}) aus Finesse passt nicht zum Steuercode ({1})'
                                            .format(steuer_konto, steuercode))
                return False
            self.steuer_konto = steuer_konto
            self.steuer_konto_name = value_dict[u'Bezeichnung Steuerkonto']
            self.steuer_betrag_soll = decimal_with_decimalcomma(value_dict[u'Steuerbetrag Soll'])
            self.steuer_betrag_haben = decimal_with_decimalcomma(value_dict[u'Steuerbetrag Haben'])
            self.mwst_satz = self.steuerfall.ust_satz
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
        # Start with an empty VF_Buchung
        result = VF_Buchung.VF_Buchung()
        result.vf_nr = self.vf_nr
        result.datum = self.datum
        result.konto = self.konto_haben
        result.konto_kostenstelle = self.konto_haben_kostenstelle
        result.gegen_konto = self.konto_soll
        result.gegen_konto_kostenstelle = self.konto_soll_kostenstelle
        result.betrag = Decimal(0)
        result.steuer_konto = self.steuer_konto
        result.mwst_satz = self.mwst_satz
        result.steuerfall = self.steuerfall
        result.buchungstext = self.buchungstext
        # result.vf_belegnummer = None
        return result

    def prepare_for_vf(self, konten_mit_kostenstelle):
        """
        :rtype: bool
        """
        # Kostenstelle einem Konto zuordnen:
        assert not self.konto_haben_kostenstelle
        assert not self.konto_soll_kostenstelle

        if not self.kostenstelle:
            return True

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

    def vf_buchung_for_export(self, konten_finesse_nach_vf, konten_mit_kostenstelle, steuer_configuration):
        assert self.finesse_buchungs_journal == finesse_fournal_for_export_to_vf

        if not self.prepare_for_vf(konten_mit_kostenstelle):
            return None

        result = VF_Buchung.VF_Buchung()

        # Wenn es die Freiheit gibt (keine Steuer) ordnen wir das Mitgliederkonto dem "Konto" zu, so dass es im
        # Journal des VF möglichst links steht.
        konto_im_haben = konten_finesse_nach_vf.enthaelt_konto(self.konto_haben)
        if self.has_steuer and self.steuer_betrag_haben != Decimal(0):
            konto_im_haben = False

        if konto_im_haben:
            result.konto = self.konto_haben
            result.konto_kostenstelle = self.konto_haben_kostenstelle
            result.gegen_konto = self.konto_soll
            result.gegen_konto_kostenstelle = self.konto_soll_kostenstelle
            result.betrag = self.betrag_haben
            #if self.has_steuer:
            #    result.steuer_konto = self.steuer_konto # TODO: map to correct Konto
        else:
            result.konto = self.konto_soll
            result.konto_kostenstelle = self.konto_soll_kostenstelle
            result.gegen_konto = self.konto_haben
            result.gegen_konto_kostenstelle = self.konto_haben_kostenstelle
            result.betrag = -self.betrag_soll
            #if self.has_steuer:
            #    result.steuer_konto = self.steuer_konto # TODO: map to correct Konto

        if self.steuerfall:
            if self.steuerfall.art == Configuration.steuerart.Vorsteuer:
                result.steuer_konto = steuer_configuration.vf_vorsteuer_konto
            elif self.steuerfall.art == Configuration.steuerart.Umsatzsteuer:
                result.steuer_konto = steuer_configuration.vf_umsatzsteuer_konto

        result.vf_nr = self.vf_nr
        result.datum = self.datum
        result.mwst_satz = self.mwst_satz
        result.buchungstext = self.buchungstext
        result.vf_belegart = VF_Buchung.vf_belegart_for_import_from_finesse
        result.vf_belegnummer = CheckDigit.append_checkdigit(unicode(self.finesse_journalnummer))

        return result

    @property
    def has_steuer(self):
        """
        :rtype: bool
        """
        return self.steuer_konto != None

    def matches_buchung(self, other_buchung):
        """
        :type other_buchung: Finesse_Buchung
        :param other_buchung: Finesse_Buchung
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
        :param other_buchung:Finesse_Buchung
        :rtype: bool
        """
        return (self.konto_haben == other_buchung.konto_haben
            and self.konto_soll == other_buchung.konto_soll)

    @classmethod
    def fieldnames_for_export_to_finesse(cls):
        return [u'Datum',u'Buchungstext',u'Betrag',u'USt-Code',u'Betrag USt',u'Konto Haben',u'Konto Soll',u'Kostenrechnungsobjekt 1',u'Rechnungsnummer',u'Belegnummer 1',u'VF_Nr']

    @property
    def dict_for_export_to_finesse(self):
        """
        :rtype: dict
        """
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
