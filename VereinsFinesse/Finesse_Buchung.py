# -*- coding: utf-8 -*-

import string
import copy
import re
import math
import decimal
from decimal import Decimal
import Configuration
import CheckDigit
import Kern_Buchung
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

    def __init__(self, konfiguration):
        """
        :param konfiguration: Configuration.Konfiguration
        """
        assert konfiguration
        self.konfiguration = konfiguration
        self.vf_nr = None
        self.finesse_buchungs_journal = None
        self.finesse_journalnummer = None
        self.finesse_steuercode = None
        self.kern_buchung = None

        # Die VF-Buchung, von der diese bei einem früheren Abgleich importiert wurde.
        self.original_vf_buchung = None
        # VF-Buchung, die von dieser bei einem früheren Abgleich kopiert wurde.
        self.kopierte_vf_buchung = None

        self.fehler_beschreibung = None

    def init_from_finesse(self, value_dict):
        assert self.kern_buchung is None  # the instance must be empty so far

        self.source_values = value_dict

        journal_name = value_dict[u'Buchungs-Journal']
        self.finesse_buchungs_journal = journal_name
        self.fehler_beschreibung, self.finesse_journalnummer = Kern_Buchung.int_from_string(value_dict[u'Journalnummer'], False, False, u'Journalnummer')
        if self.fehler_beschreibung:
            return False
        # Feststellen, ob diese Buchung ursprünglich vom VF importiert wurde.
        beleg2_text = value_dict[u'Beleg 2']
        # Anfang 2016 haben einige Buchungen in Finesse kleine Zahlen in Beleg 2 bekommen
        # Daher Heuristik, um 6-stellige VF-Buchungsnummern zu erkennen.
        if len(beleg2_text) >= 6:
            vf_nr_text = CheckDigit.check_and_strip_checkdigit(beleg2_text)
            if not vf_nr_text:
                self.fehler_beschreibung = u'Falsche Prüfziffer für VF-Nr in Belegnummer 2({0})'.format(beleg2_text)
                return False
            self.fehler_beschreibung, self.vf_nr = Kern_Buchung.int_from_string(vf_nr_text, False, False, u'Vereinsflieger-Nr.')
            if self.fehler_beschreibung:
                return False

        self.kern_buchung = self.kern_buchung_from_finesse_export(value_dict);
        if not self.kern_buchung:
            return False

        return True

    def kern_buchung_from_finesse_export(self, value_dict):
        kern_buchung = Kern_Buchung.Kern_Buchung()

        kern_buchung.datum = value_dict[u'Belegdatum']
        kern_buchung.buchungstext = value_dict[u'Buchungs-Text']

        self.fehler_beschreibung, konto = Kern_Buchung.int_from_string(value_dict[u'Konto Soll'], False, False, u'Konto Soll')
        if self.fehler_beschreibung:
            return None
        kern_buchung.konto_soll = self.konfiguration.konto_from_finesse_konto(konto)
        kern_buchung.konto_soll_name = value_dict[u'Bezeichnung Konto Soll']

        self.fehler_beschreibung, konto = Kern_Buchung.int_from_string(value_dict[u'Konto Haben'], False, False, u'Konto Haben')
        if self.fehler_beschreibung:
            return None
        kern_buchung.konto_haben = self.konfiguration.konto_from_finesse_konto(konto)
        kern_buchung.konto_haben_name = value_dict[u'Bezeichnung Konto Haben']

        # Finesse schreibt "000000000" für leere Kostenstellen, wird auf None abgebildet.
        self.fehler_beschreibung, kostenstelle = Kern_Buchung.int_from_string(value_dict[u'Kostenrechnung 1'], True, True, u'Kostenstelle')
        if self.fehler_beschreibung:
            return None
        kern_buchung.kostenstelle = self.konfiguration.kostenstelle_from_finesse_kostenstelle(kostenstelle)

        kern_buchung.betrag_soll = decimal_with_decimalcomma(value_dict[u'Betrag Soll'])
        kern_buchung.betrag_haben = decimal_with_decimalcomma(value_dict[u'Betrag Haben'])

        # Finesse exportiert '0' für 'kein Konto'
        self.fehler_beschreibung, steuer_konto  = Kern_Buchung.int_from_string(value_dict[u'Steuerkonto'], True, True, u'Steuerkonto')
        if self.fehler_beschreibung:
            return None
        steuercode_text = value_dict[u'Steuercode']
        if len(steuercode_text) > 0:
            self.fehler_beschreibung, steuercode = Kern_Buchung.int_from_string(steuercode_text, False, False, u'Steuercode')
            if self.fehler_beschreibung:
                return None
            kern_buchung.steuerfall = self.konfiguration.steuer_configuration.steuerfall_for_finesse_steuercode(steuercode)
            if not kern_buchung.steuerfall:
                self.fehler_beschreibung = u'Unbekannter Steuercode ({0})'.format(steuercode)
                return None

            # Das Steuerkonto aus Finesse muss zum Steuercode passen.
            if steuer_konto != kern_buchung.steuerfall.konto_finesse:
                self.fehler_beschreibung = (u'Steuerkonto ({0}) aus Finesse passt nicht zum Steuercode ({1})'
                                            .format(steuer_konto, steuercode))
                return None

            kern_buchung.steuer_betrag_soll = decimal_with_decimalcomma(value_dict[u'Steuerbetrag Soll'])
            kern_buchung.steuer_betrag_haben = decimal_with_decimalcomma(value_dict[u'Steuerbetrag Haben'])
        else:
            # Kein Steuercode angegeben, dann muss das übrige Steuerzeugs leer oder 0 sein.
            if (   steuer_konto != None
                or decimal_with_decimalcomma(value_dict[u'Steuerbetrag Soll']) != Decimal(0)
                or decimal_with_decimalcomma(value_dict[u'Steuerbetrag Haben']) != Decimal(0)):
                self.fehler_beschreibung = u'Kein Steuercode, aber andere Steuerangaben sind nicht alle 0'
                return None
            if kern_buchung.betrag_soll != kern_buchung.betrag_haben:
                self.fehler_beschreibung = u'Buchung ohne Steuer hat differierende Soll- und Habenbeträge'
                return None

        kern_buchung.rechnungsnummer = value_dict[u'Rechnungsnummer']   # Die Rechnungs"nummer" kann beliebiger Text sein
        #TODO: kern_buchung.belegnummer

        kern_buchung.check_kostenstelle(self.konfiguration)

        return kern_buchung

    @property
    def kompatible_buchungen_key(self):
        """
        Leitet an die Kernbuchung weiter unter Berücksichtigung der Konfigurationseinstellung für Kostenstellen.
        """
        return self.kern_buchung.kompatible_buchungen_key(not self.konfiguration.ignoriere_aenderung_der_kostenstelle)

    def create_placeholder_for_deleted_vf_buchung(self):
        # Start with an empty VF_Buchung
        result = VF_Buchung.VF_Buchung(self.konfiguration)

        result.kern_buchung = copy.copy(self.kern_buchung)
        result.kern_buchung.buchungstext = u'Storno wegen Löschung im VF: {0}'.format(self.kern_buchung.buchungstext)
        result.kern_buchung.betrag_soll = Decimal(0)
        result.kern_buchung.betrag_haben = Decimal(0)
        result.kern_buchung.steuer_betrag_soll = Decimal(0)
        result.kern_buchung.steuer_betrag_haben = Decimal(0)
        result.vf_nr = self.vf_nr
        return result

    @property
    def ist_valide_fuer_export_nach_vf(self):
        """
        :rtype: bool
        """
        fehler_beschreibung = self.kern_buchung.fehler_beschreibung_fuer_export_nach_vf(self.konfiguration)
        if fehler_beschreibung is None:
            return True
        self.fehler_beschreibung = fehler_beschreibung
        return False

    @property
    def dict_for_export_to_vf(self):
        """
        :rtype: dict
        """

        assert self.finesse_buchungs_journal == finesse_fournal_for_export_to_vf

        result = self.kern_buchung.dict_for_export_to_vf(self.konfiguration)
        result[u'BelegArt'] = VF_Buchung.vf_belegart_for_import_from_finesse
        result[u'BelegNr']  = CheckDigit.append_checkdigit(unicode(self.finesse_journalnummer))
        return result

    @classmethod
    def fieldnames_for_export_to_finesse(cls):
        return [u'Datum',u'Buchungstext',u'Betrag',u'USt-Code',u'Betrag USt',u'Konto Haben',u'Konto Soll',u'Kostenrechnungsobjekt 1',u'Rechnungsnummer',u'Belegnummer 1',u'VF_Nr']

    def lookup_storno_partner(self, storno_candidates):
        """
        storno_candidates ist eine liste von Buchungen mit gleichem konten_key wie diese Buchung.
        Suche die erste Buchung aus dieser Liste, die diese Buchung storniert, das heißt, ihren Effekt umkehrt.
        """
        for candidate in storno_candidates:
            if self.kern_buchung.ist_storno_gegen(candidate.kern_buchung):
                return candidate
        return None
