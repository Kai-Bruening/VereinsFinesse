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
        self.steuer_betrag_soll = Decimal(0)
        self.steuer_betrag_haben = Decimal(0)
        self.mwst_satz = None
        self.rechnungsnummer = None
        self.steuerfall = None
        self.vf_konto_ist_konto_haben = None

        self.kern_buchung = None

        # Die VF-Buchung, von der diese bei einem früheren Abgleich importiert wurde.
        self.original_vf_buchung = None
        # VF-Buchung, die von dieser bei einem früheren Abgleich kopiert wurde.
        self.kopierte_vf_buchung = None

        self.fehler_beschreibung = None

    def init_from_finesse(self, value_dict):
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

        self.kern_buchung = self.kern_buchung_from_finesse_export(value_dict);
        if not self.kern_buchung:
            return False

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
            self.steuerfall = self.konfiguration.steuer_configuration.steuerfall_for_finesse_steuercode(steuercode)
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

        if self.has_steuer:
            # Im VF ist 'Betrag' immer der Bruttobetrag, der damit auf 'Konto' gebucht wird.
            # Das heißt, 'Konto' ist das Haben-Konto wenn die Steuer im Soll gebucht wird.
            self.vf_konto_ist_konto_haben = self.steuer_betrag_haben == Decimal(0)
        else:
            # Wenn es die Freiheit gibt (keine Steuer) ordnen wir das Mitgliederkonto dem VF-'Konto' zu, so dass
            # es im Journal des VF möglichst links steht.
            self.vf_konto_ist_konto_haben = self.konfiguration.konten_finesse_nach_vf.enthaelt_konto(self.konto_haben)

        return True

    def kern_buchung_from_finesse_export(self, value_dict):
        kern_buchung = Kern_Buchung.Kern_Buchung()

        kern_buchung.datum = value_dict[u'Belegdatum']
        kern_buchung.buchungstext = value_dict[u'Buchungs-Text']
        kern_buchung.konto_soll = self.konfiguration.konto_from_finesse_konto(int(value_dict[u'Konto Soll']))
        kern_buchung.konto_soll_name = value_dict[u'Bezeichnung Konto Soll']
        kern_buchung.konto_haben = self.konfiguration.konto_from_finesse_konto(int(value_dict[u'Konto Haben']))
        kern_buchung.konto_haben_name = value_dict[u'Bezeichnung Konto Haben']

        kern_buchung.kostenstelle = int(value_dict[u'Kostenrechnung 1'])
        # Finesse schreibt "000000000" für leere Kostenstellen.
        if kern_buchung.kostenstelle == 0:
            kern_buchung.kostenstelle = None

        kern_buchung.betrag_soll = decimal_with_decimalcomma(value_dict[u'Betrag Soll'])
        kern_buchung.betrag_haben = decimal_with_decimalcomma(value_dict[u'Betrag Haben'])

        # Finesse exportiert '0' für 'kein Konto'
        steuer_konto = int(value_dict[u'Steuerkonto'])
        steuercode_text = value_dict[u'Steuercode']
        if len(steuercode_text) > 0:
            steuercode = int(steuercode_text)
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
            # Kein Steuercode angegeben, dann müssen das übrige Steuerzeugs leer oder 0 sein.
            if (   steuer_konto != 0
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

    def validate_for_original_vf_buchung(self, original_vf_buchung):
        # Buchungen im VF können jederzeit vom Betrag her geändert werden, aber die Konten und andere
        # Daten müssen bleiben.
        if self.steuerfall != original_vf_buchung.steuerfall:
            return False
        #if original_vf_buchung.is_null:
        # Im entarteten Fall ist die Zuordnung der Konten in VF zu Soll und Haben nicht definiert.
        return ((self.konto_haben == original_vf_buchung.konto_for_finesse
                and self.konto_soll == original_vf_buchung.gegen_konto_for_finesse)
            or (self.konto_soll == original_vf_buchung.konto_for_finesse
                and self.konto_haben == original_vf_buchung.gegen_konto_for_finesse))
        # test_finesse_buchung = original_vf_buchung.finesse_buchung_from_vf_buchung()
        # return (self.konto_haben == test_finesse_buchung.konto_haben
        #     and self.konto_soll == test_finesse_buchung.konto_soll)

    def create_placeholder_for_deleted_vf_buchung(self):
        self.prepare_for_vf()
        # Start with an empty VF_Buchung
        result = VF_Buchung.VF_Buchung(self.konfiguration)

        result.kern_buchung = copy.copy(self.kern_buchung)
        result.kern_buchung.buchungstext = u'Storno wegen Löschung im VF: {0}'.format(self.buchungstext)
        result.kern_buchung.betrag_soll = Decimal(0)
        result.kern_buchung.betrag_haben = Decimal(0)
        result.kern_buchung.steuer_betrag_soll = Decimal(0)
        result.kern_buchung.steuer_betrag_haben = Decimal(0)

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
        result.buchungstext = u'Storno wegen Löschung im VF: {0}'.format(self.buchungstext)
        # result.vf_belegnummer = None
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

    def prepare_for_vf(self):
        """
        :rtype: bool
        """
        # Kostenstelle einem Konto zuordnen:
        # assert not self.konto_haben_kostenstelle
        # assert not self.konto_soll_kostenstelle
        #
        # if not self.kostenstelle:
        #     return True
        #
        # if self.konfiguration.konten_mit_kostenstelle.enthaelt_konto(self.konto_soll):
        #     if self.konfiguration.konten_mit_kostenstelle.enthaelt_konto(self.konto_haben):
        #         self.fehler_beschreibung = u'Buchung von Erfolgskonto zu Erfolgskonto, keine Zuordnung der Kostenstelle für Export zu VF möglich'
        #         return False
        #     self.konto_soll_kostenstelle = self.kostenstelle
        # elif self.konfiguration.konten_mit_kostenstelle.enthaelt_konto(self.konto_haben):
        #     self.konto_haben_kostenstelle = self.kostenstelle
        # elif (self.konfiguration.vf_konten_die_kostenstelle_ignorieren.enthaelt_konto(self.konto_soll_for_vf)
        #     or self.konfiguration.vf_konten_die_kostenstelle_ignorieren.enthaelt_konto(self.konto_haben_for_vf)):
        #     pass
        # else:
        #     self.fehler_beschreibung = u'Kostenstelle kann für Export zu VF keinem der Konten zugeordnet werden'
        #     return False

        return True

    # def vf_buchung_for_export(self):
    #     assert self.finesse_buchungs_journal == finesse_fournal_for_export_to_vf
    #
    #     if not self.prepare_for_vf():
    #         return None
    #
    #     result = VF_Buchung.VF_Buchung(self.konfiguration)
    #     result.kern_buchung = copy.copy(self.kern_buchung)
    #
    #     # Der Normalfall ist, das Habenkonto auf 'Konto' im VF abzubilden. Bei positivem Betrag wird dieses Konto
    #     # vom VF als Habenkonto angezeigt.
    #     konto_im_haben = True
    #     if self.steuerfall:
    #         # Der Bruttobetrag muss immer auf das Konto gebucht werden, der Nettobetrag auf das Gegenkonto.
    #         if abs (self.betrag_soll) > abs (self.betrag_haben):
    #             konto_im_haben = False
    #     else:
    #         if self.betrag_soll != self.betrag_haben:
    #             self.fehler_beschreibung = u'Buchung ohne Steuer hat differierende Soll- und Habenbeträge'
    #             return None
    #
    #     # Notiz: früher haben wir Mitgliedskonten möglichst dem "Konto" zugeordnet, damit sie im Journal des VF
    #     # möglichst links stehen. Das bringt seit der Umstellung auf Soll- und Haben-Darstellung nichts mehr und
    #     # ist daher weg.
    #
    #     if konto_im_haben:
    #         result.konto = self.konto_haben_for_vf
    #         result.konto_kostenstelle = self.konto_haben_kostenstelle
    #         result.gegen_konto = self.konto_soll_for_vf
    #         result.gegen_konto_kostenstelle = self.konto_soll_kostenstelle
    #         result.betrag = self.betrag_haben
    #     else:
    #         result.konto = self.konto_soll_for_vf
    #         result.konto_kostenstelle = self.konto_soll_kostenstelle
    #         result.gegen_konto = self.konto_haben_for_vf
    #         result.gegen_konto_kostenstelle = self.konto_haben_kostenstelle
    #         result.betrag = -self.betrag_soll
    #
    #     if self.steuerfall:
    #         if self.steuerfall.art == Configuration.steuerart.Vorsteuer:
    #             result.steuer_konto = self.konfiguration.steuer_configuration.vf_vorsteuer_konto
    #         elif self.steuerfall.art == Configuration.steuerart.Umsatzsteuer:
    #             result.steuer_konto = self.konfiguration.steuer_configuration.vf_umsatzsteuer_konto
    #
    #     result.vf_nr = self.vf_nr
    #     result.datum = self.datum
    #     result.mwst_satz = self.mwst_satz
    #     result.buchungstext = self.buchungstext
    #     result.vf_belegart = VF_Buchung.vf_belegart_for_import_from_finesse
    #     result.vf_belegnummer = CheckDigit.append_checkdigit(unicode(self.finesse_journalnummer))
    #
    #     return result

    @property
    def dict_for_export_to_vf(self):
        """
        :rtype: dict
        """

        assert self.finesse_buchungs_journal == finesse_fournal_for_export_to_vf

        # if not self.prepare_for_vf():
        #     return None

        result = self.kern_buchung.dict_for_export_to_vf(self.konfiguration)
        result[u'BelegArt'] = VF_Buchung.vf_belegart_for_import_from_finesse
        result[u'BelegNr']  = CheckDigit.append_checkdigit(unicode(self.finesse_journalnummer))
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

    def anti_matches_konten_of_buchung(self, other_buchung):
        """
        :param other_buchung:Finesse_Buchung
        :rtype: bool
        """
        return (self.konto_haben == other_buchung.konto_soll
            and self.konto_soll == other_buchung.konto_haben)

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
        result[u'Konto Haben'] = self.konto_haben
        result[u'Konto Soll'] = self.konto_soll

        # Der Text-Import nach Finesse kennt nur einen Betrag und einen Steuerbetrag ohne Aufteilung nach Soll und
        # Haben. Es stellt sich heraus, dass der Betrag immer der Bruttobetrag ist. Die Zuordnung der Steuer zum
        # richtigen Konto erfolgt automatisch basierend auf dem beteiligten Aufwands- oder Ertragskonto.
        # Der Normalfall ist dabei, dass Umsatzsteuer im Haben und Vorsteuer im Soll gebucht wird.

        result[u'Betrag'] = self.betrag_soll
        if self.steuer_betrag_haben and self.steuer_betrag_haben != Decimal(0):
            assert self.steuer_betrag_soll == Decimal(0)
            # Steuer wird auf der Habenseite verbucht, also ist der Bruttobetrag im Soll.
            result[u'Betrag USt'] = self.steuer_betrag_haben
            result[u'Betrag'] = self.betrag_soll
        elif self.steuer_betrag_soll and self.steuer_betrag_soll != Decimal(0):
            # Steuer wird auf der Sollseite verbucht, also ist der Bruttobetrag im Haben.
            result[u'Betrag USt'] = self.steuer_betrag_soll
            result[u'Betrag'] = self.betrag_haben
        else:
            assert self.betrag_soll == self.betrag_haben
            result[u'Betrag'] = self.betrag_soll

        if self.steuerfall:
            result[u'USt-Code'] = self.steuerfall.code

        #if self.has_steuer and self.finesse_steuercode != 1:
        #    result[u'USt-Code'] = self.finesse_steuercode

        if self.kostenstelle:
            result[u'Kostenrechnungsobjekt 1'] = self.kostenstelle
        if self.rechnungsnummer:
            result[u'Rechnungsnummer'] = self.rechnungsnummer
        if self.vf_belegnummer:
            result[u'Belegnummer 1'] = self.vf_belegnummer
        result[u'VF_Nr'] = CheckDigit.append_checkdigit(unicode(self.vf_nr))

        return result

    # @property
    # def konten_key(self):
    #     # Vertauschte Konten müssen den gleichen Schlüssel ergeben.
    #     if self.konto_haben < self.konto_soll:
    #         konto1 = self.konto_haben
    #         konto2 = self.konto_soll
    #     else:
    #         konto1 = self.konto_soll
    #         konto2 = self.konto_haben
    #     return konto1, konto2, self.kostenstelle

    # @property
    # def kompatible_buchungen_key(self):
    #     steuercode = None
    #     if self.steuerfall:
    #         steuercode = self.steuerfall.code
    #     return self.konten_key + (steuercode , )

    def lookup_storno_partner(self, storno_candidates):
        """
        storno_candidates ist eine liste von Buchungen mit gleichem konten_key wie diese Buchung.
        Suche die erste Buchung aus dieser Liste, die diese Buchung storniert, das heißt, ihren Effekt umkehrt.
        """
        for candidate in storno_candidates:
            if candidate.konto_soll == self.konto_soll:
                # Wenn die Konten gleich sind, müssen die Beträge entgegengesetzt sein.
                if (candidate.betrag_soll == -self.betrag_soll and
                        candidate.betrag_haben == -self.betrag_haben and
                        (not self.steuerfall or
                             (candidate.steuer_betrag_soll == -self.steuer_betrag_soll and
                              candidate.steuer_betrag_haben == -self.steuer_betrag_haben))):
                    return candidate
            else:
                # Andernfalls müssen die Beträge bei vertauschten Konten gleich sein.
                if (candidate.betrag_soll == self.betrag_haben and
                            candidate.betrag_haben == self.betrag_soll and
                            candidate.steuer_betrag_soll == self.steuer_betrag_haben and
                            candidate.steuer_betrag_haben == self.steuer_betrag_soll):
                    return candidate
        return None

    def subtract_betraege_von(self, andere_buchung):
        if andere_buchung.matches_konten_of_buchung(self):
            self.betrag_soll -= andere_buchung.betrag_soll
            self.betrag_haben -= andere_buchung.betrag_haben
            if self.has_steuer:
                assert (self.steuer_betrag_soll == Decimal(0)) or (andere_buchung.steuer_betrag_haben == Decimal(0))
                assert (self.steuer_betrag_haben == Decimal(0)) or (andere_buchung.steuer_betrag_soll == Decimal(0))
                self.steuer_betrag_soll -= andere_buchung.steuer_betrag_soll
                self.steuer_betrag_haben -= andere_buchung.steuer_betrag_haben
        else:
            # TODO: unit test for this case
            assert andere_buchung.anti_matches_konten_of_buchung(self)
            self.betrag_soll += andere_buchung.betrag_haben
            self.betrag_haben += andere_buchung.betrag_soll
            if self.has_steuer:
                assert (self.steuer_betrag_soll == Decimal(0)) or (andere_buchung.steuer_betrag_soll == Decimal(0))
                assert (self.steuer_betrag_haben == Decimal(0)) or (andere_buchung.steuer_betrag_haben == Decimal(0))
                self.steuer_betrag_soll += andere_buchung.steuer_betrag_haben
                self.steuer_betrag_haben += andere_buchung.steuer_betrag_soll
