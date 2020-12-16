# -*- coding: utf-8 -*-

import string
import copy
import re
import math
import decimal
from decimal import Decimal
import datetime
import Configuration
import CheckDigit
import Kern_Buchung
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
        self.vf_belegart = None
        self.kern_buchung = None
        self.finesse_journalnummer = None

        # Die Finesse-Buchung, von der dieser bei einem früheren Abgleich importiert wurde.
        self.original_finesse_buchung = None

        # Finesse-Buchungen, die von dieser bei früheren Abgleichen kopiert wurden (mehrere bei Änderungen im VF).
        self.kopierte_finesse_buchungen_by_kompatible_buchungen_key = {}

        self.fehler_beschreibung = None

    def init_from_vf(self, value_dict):
        """
        :param value_dict: Dict
        :rtype: bool
        """
        assert self.kern_buchung is None  # the instance must be empty so far

        # Die Quellwerte werden für den Fall einer Fehlerausgabe gemerkt.
        self.source_values = value_dict

        self.kern_buchung = self.kern_buchung_from_vf_export(value_dict)
        if not self.kern_buchung:
            return False

        self.fehler_beschreibung, self.vf_nr = Kern_Buchung.int_from_string(value_dict[u'Nr'], False, False, u'Nr.')
        if self.fehler_beschreibung:
            return None
        self.vf_belegart = value_dict[u'Belegart']
        belegnummer_text = value_dict[u'Belegnummer']
        # Feststellen, ob diese Buchung ursprünglich von Finesse importiert wurde.
        if self.vf_belegart == vf_belegart_for_import_from_finesse:
            finesse_journal_nummer_text = CheckDigit.check_and_strip_checkdigit(belegnummer_text)
            if not finesse_journal_nummer_text:
                self.fehler_beschreibung = u'Falsche Prüfziffer für Finesse Journalnummer in Belegnummer ({0})'.format(belegnummer_text)
                return False
            self.fehler_beschreibung, self.finesse_journalnummer = Kern_Buchung.int_from_string(finesse_journal_nummer_text, False, False,
                                                                           u'Finesse Journalnummer')
            if self.fehler_beschreibung:
                return None
        else:
            self.fehler_beschreibung, self.kern_buchung.belegnummer = Kern_Buchung.int_from_string(belegnummer_text, False, False, u'Belegnummer')
            if self.fehler_beschreibung:
                return None

        return True

    def kern_buchung_from_vf_export(self, value_dict):
        kern_buchung = Kern_Buchung.Kern_Buchung()
        kern_buchung.buchungstext = value_dict[u'Buchungstext']

        #kern_buchung.datum = value_dict[u'Datum']
        text_datum = value_dict[u'Datum']
        try:
            kern_buchung.datum = datetime.datetime.strptime(text_datum, '%d.%m.%Y').date()
        except:
            self.fehler_beschreibung = u'Datum ({0}) nicht erkannt'.format(text_datum)
            return None

        self.fehler_beschreibung, (konto, konto_kostenstelle) = vf_read_konto(value_dict[u'Konto'], u'Konto')
        if self.fehler_beschreibung:
            return None

        self.fehler_beschreibung, (gegen_konto, gegen_konto_kostenstelle) = vf_read_konto(value_dict[u'G-Konto'], u'Gegenkonto')
        if self.fehler_beschreibung:
            return None

        # Im Vereinsflieger ist es irgendwie tatsächlich möglich, Buchungen mit identischen Konten einzugeben.
        if gegen_konto == konto:
            self.fehler_beschreibung = u'Identisches Konto ({0}) auf beiden Seiten der Buchung'.format(konto)
            return None

        konto = self.konfiguration.konto_from_vf_konto(konto)
        gegen_konto = self.konfiguration.konto_from_vf_konto(gegen_konto)
        # Das Kontomapping könnte ebenfalls die Konten gleich machen, also checke ich lieber noch mal.
        if gegen_konto == konto:
            self.fehler_beschreibung = u'Identisches Konto ({0}) auf beiden Seiten der Buchung nach Kontenmapping'.format(konto)
            return None

        self.fehler_beschreibung, kostenstelle = Kern_Buchung.int_from_string(value_dict[u'Kostenstelle'], True, True, u'Kostenstelle')
        if self.fehler_beschreibung:
            return None
        kern_buchung.kostenstelle = self.konfiguration.kostenstelle_from_vf_kostenstelle(kostenstelle)

        #betrag = decimal_with_decimalcomma(value_dict[u'Betrag'])
        betrag_konto = decimal_with_decimalcomma(value_dict[u'Betrag(Konto)'])
        betrag_gegen_konto = decimal_with_decimalcomma(value_dict[u'Betrag(G-Konto)'])
        betrag_steuer_konto = decimal_with_decimalcomma(value_dict[u'Betrag(S-Konto)'])

        steuer_satz = Decimal(0)
        steuer_satz_text = value_dict[u'MwSt(%)']
        steuer_konto_text = value_dict[u'S-Konto']
        if len(steuer_konto_text) > 0:
            self.fehler_beschreibung, steuer_konto = Kern_Buchung.int_from_string(steuer_konto_text, False, False,
                                                                           u'Steuerkonto')
            if self.fehler_beschreibung:
                return None
            steuer_satz = Decimal(steuer_satz_text)
            kern_buchung.steuerfall = self.konfiguration.steuer_configuration.steuerfall_for_vf_steuerkonto_and_steuersatz(steuer_konto, steuer_satz)
            if not kern_buchung.steuerfall:
                self.fehler_beschreibung = u'Kombination aus Steuerkonto ({0}) und Steuersatz ({1}%) unbekannt'.format(steuer_konto, steuer_satz)
                return None

            # Der Steuersatz aus dem Vereinsflieger muss zum Steuerkonto passen.
            if (steuer_satz != kern_buchung.steuerfall.ust_satz
                and not (steuer_satz == Decimal(0) and not kern_buchung.steuerfall.ust_satz)):
                self.fehler_beschreibung = (u'MwSt-Satz ({0}) aus Vereinsflieger passt nicht zum dem des Steuerkontos ({1})'
                                            .format(steuer_satz, kern_buchung.steuerfall.ust_satz))
                return None
        else:
            # Kein Steuerkonto angegeben, dann muss der MwSt-Satz 0 sein (oder leer).
            if len(steuer_satz_text) > 0 and Decimal(steuer_satz_text) != Decimal(0):
                self.fehler_beschreibung = u'MwSt-Satz > 0 ({0}) ohne Steuerkonto'.format(steuer_satz_text)
                return None
            if betrag_konto != -betrag_gegen_konto:
                self.fehler_beschreibung = u'Buchung ohne Steuer hat differierende Soll- und Habenbeträge'
                return None

        # Wir nehmen immer die Zuordnung, die zu positiven Beträgen in der Buchung führt, so wie es VF anzeigt.
        # Wenn der Betrag 0 ist, wird das Konto zum Habenkonto.
        konto_ist_haben = betrag_konto >= Decimal(0)
        betrag_steuer_ins_haben = False
        if abs(betrag_konto) != abs(betrag_gegen_konto):
            # Wenn die Buchung einen Steuerbetrag enthält, ist die Zuordnung zu Soll und Haben zwingend nach der
            # Finesse-Regel:
            #   Vorsteuer: Haben Brutto, Soll Netto
            #   U-St:      Soll Brutto, Haben Netto
            konto_ist_brutto = abs(betrag_konto) > abs(betrag_gegen_konto)
            steuerart = Configuration.steuerart.Keine
            if kern_buchung.steuerfall:
                steuerart = kern_buchung.steuerfall.art
            if steuerart == Configuration.steuerart.Keine:
                self.fehler_beschreibung = u'Ungleiche Beträge ohne Angabe einer Steuerart'
                return None
            f_konto_ist_haben = konto_ist_brutto if steuerart == Configuration.steuerart.Vorsteuer else not konto_ist_brutto

            betrag_steuer_ins_haben = steuerart == Configuration.steuerart.Umsatzsteuer
            if konto_ist_haben != f_konto_ist_haben:
                betrag_steuer_ins_haben = not betrag_steuer_ins_haben
            if betrag_steuer_ins_haben:
                kern_buchung.steuer_betrag_haben = betrag_steuer_konto
            else:
                kern_buchung.steuer_betrag_soll  = -betrag_steuer_konto
        # else:
        #     # Ohne Steuer nehmen wir die Zuordnung, die zu positiven Beträgen in der Buchung führt.
        #     # Wenn der Betrag 0 ist, wird das Konto zum Habenkonto.
        #     konto_ist_haben = betrag_konto >= Decimal(0)

        kern_buchung.konto_soll = gegen_konto if konto_ist_haben else konto
        kern_buchung.konto_haben = konto if konto_ist_haben else gegen_konto
        kern_buchung.betrag_soll = -(betrag_gegen_konto if konto_ist_haben else betrag_konto)
        kern_buchung.betrag_haben = betrag_konto if konto_ist_haben else betrag_gegen_konto

        kern_buchung.rechnungsnummer = value_dict[u'Abrechnungsnr']   # Die Rechnungs"nummer" kann beliebiger Text sein
        #TODO: kern_buchung.belegnummer

        return kern_buchung

    @property
    def kompatible_buchungen_key(self):
        """
        Leitet an die Kernbuchung weiter unter Berücksichtigung der Konfigurationseinstellung für Kostenstellen.
        """
        return self.kern_buchung.kompatible_buchungen_key(not self.konfiguration.ignoriere_aenderung_der_kostenstelle)

    def validate_for_original_finesse_buchung(self, original_finesse_buchung):
        if self.kern_buchung.is_null:    # muss zuerst gecheckt werden, weil die anderen Checks das voraussetzen
            assert original_finesse_buchung.betrag != Decimal(0)    # Finesse kennt keine Buchungen mit Betrag 0
            return False

        if self.kern_buchung.matches_buchung(original_finesse_buchung.kern_buchung):
            return True

        test_buchung = self.kern_buchung.buchung_mit_getauschten_konten()
        return test_buchung.matches_buchung(original_finesse_buchung.kern_buchung)

    def connect_kopierte_finesse_buchung(self, finesse_buchung):
        # Finesse scheint beim Import eine Kostenstelle hinzuzufügen, wenn Splitbuchungen importiert werden. Das muss
        # noch näher untersucht werden, aber zur Zeit ignorieren wir die Kostenstelle in der Finesse-Buchung, wenn die
        # VF-Buchung keine hat.
        #TODO: needs a test
        if not self.kern_buchung.kostenstelle:
            finesse_buchung.kern_buchung.kostenstelle = None

        # Wir bilden Gruppen von kompatiblen Finesse-Buchungen, die untereinander konsolidiert werden können.
        kompatible_buchungen_key = finesse_buchung.kompatible_buchungen_key
        if kompatible_buchungen_key in self.kopierte_finesse_buchungen_by_kompatible_buchungen_key:
            kompatible_buchungen = self.kopierte_finesse_buchungen_by_kompatible_buchungen_key[kompatible_buchungen_key]
            kompatible_buchungen.append(finesse_buchung)
            kompatible_buchungen.sort(key=lambda x: x.finesse_journalnummer)
        else:
            self.kopierte_finesse_buchungen_by_kompatible_buchungen_key[kompatible_buchungen_key] = [finesse_buchung]

        finesse_buchung.original_vf_buchung = self

    @property
    def dicts_for_export_to_finesse(self):
        """
        :rtype: list
        """
        assert self.vf_belegart != vf_belegart_for_import_from_finesse

        kompatible_finesse_buchungen_key = self.kompatible_buchungen_key

        result = []

        # Zunächst werden evt. nicht mehr kompatible Buchungen in Finesse storniert.
        for key, finesse_buchungen in self.kopierte_finesse_buchungen_by_kompatible_buchungen_key.items():
            if key != kompatible_finesse_buchungen_key:
                storno_buchung = self.kern_buchung_zum_stornieren_von_finesse_buchungen(finesse_buchungen)
                # Finesse protestiert bei Buchung mit Betrag 0, was irgendwie verständlich ist.
                if not storno_buchung.is_null:
                    result_dict = self.dict_for_export_to_finesse(storno_buchung)
                    # Selbst wenn .is_null false ist, kann der Finesseexport noch null werden
                    # durch Rundungseffekte (ein Betrag 0, der andere 0,01).
                    if result_dict != None:
                        result.append(result_dict)

        # Jetzt eine Finesse-Buchung für diese VF-Buchung erzeugen, korrigiert um evt. bereits übertragene kompatible
        # frühere Versionen der Buchung.
        kompatible_finesse_buchungen = None
        if kompatible_finesse_buchungen_key in self.kopierte_finesse_buchungen_by_kompatible_buchungen_key:
            kompatible_finesse_buchungen = self.kopierte_finesse_buchungen_by_kompatible_buchungen_key[kompatible_finesse_buchungen_key]

        export_buchung = self.kern_buchung_zum_export_nach_finesse_korrigiert_um_alte_exports(kompatible_finesse_buchungen)

        # Finesse protestiert bei Buchung mit Betrag 0, was irgendwie verständlich ist.
        if not export_buchung.is_null:
            result_dict = self.dict_for_export_to_finesse(export_buchung)
            # Selbst wenn .is_null false ist, kann der Finesseexport noch null werden
            # durch Rundungseffekte (ein Betrag 0, der andere 0,01).
            if result_dict != None:
                result.append(result_dict)

        return result

    def kern_buchung_zum_stornieren_von_finesse_buchungen(self, finesse_buchungen):
        """
        :rtype: Kern_Buchung.Kern_Buchung
        """

        # Initialisieren einer Kernbuchhung mit den Werten der ersten Finesse-Buchung ohne Beträge.
        storno_buchung = copy.copy(finesse_buchungen[0].kern_buchung)
        storno_buchung.betrag_haben = Decimal(0)
        storno_buchung.betrag_soll = Decimal(0)
        storno_buchung.steuer_betrag_haben = Decimal(0)
        storno_buchung.steuer_betrag_soll = Decimal(0)

        # Da der Effekt von finesse_buchungen entfernt werden soll, müssen alle Beträge abgezogen werden.
        for b in finesse_buchungen:
            storno_buchung.subtract_betraege_von(b.kern_buchung)

        storno_buchung.buchungstext = u'Storno wegen inkompatibler Änderung im VF: {0}'.format(
            storno_buchung.buchungstext)

        return storno_buchung

    def kern_buchung_zum_export_nach_finesse_korrigiert_um_alte_exports(self, existierende_finesse_buchungen):
        """
        :rtype: Kern_Buchung.Kern_Buchung
        """

        if self.kern_buchung.is_null:
            if existierende_finesse_buchungen:
                # Die Buchung im VF wurde auf 0 gesetzt, das ist ein entarteter Fall für die Kontenzuordnung. Daher
                # wird die Zuordnung von den existierenden Finesse Buchungen genommen.
                export_buchung = self.kern_buchung_zum_stornieren_von_finesse_buchungen(existierende_finesse_buchungen)
                export_buchung.datum = self.kern_buchung.datum
                export_buchung.buchungstext = self.kern_buchung.buchungstext
                export_buchung.rechnungsnummer = self.kern_buchung.rechnungsnummer
                export_buchung.belegnummer = self.kern_buchung.belegnummer
            else:
                export_buchung = copy.copy(self.kern_buchung)

        else:
            export_buchung = copy.copy(self.kern_buchung)

            # Wenn es bereits Buchungen in Finesse zu dieser Buchung gibt, wird der Saldo für die neue Buchung gebildet.
            if existierende_finesse_buchungen:
                for b in existierende_finesse_buchungen:
                    export_buchung.subtract_betraege_von(b.kern_buchung)

        return export_buchung

    def dict_for_export_to_finesse(self, kern_buchung):
        """
        :rtype: dict
        """
        result = kern_buchung.dict_for_export_to_finesse(self.konfiguration)
        if result != None:  # -> betrag wäre 0
            result[u'VF_Nr'] = CheckDigit.append_checkdigit(unicode(self.vf_nr))
        return result

    @classmethod
    def fieldnames_for_export_to_vf(cls):
        return [u'Datum',u'Konto',u'Betrag',u'Gegenkonto',u'Steuerkonto',u'Mwst',u'Buchungstext',u'BelegArt',u'BelegNr',u'Kostenstelle']


def vf_read_konto(dict_value, name):
    match = vf_konto_und_kostenstelle_expr.match(dict_value)
    if match:
        fehler_beschreibung = u'Vereinsflieger-Kontonummern mit Kostenstelle ({0}) dürfen ab 2018 nicht mehr verwendet werden'.format(dict_value)
        return (fehler_beschreibung, (None, None))
    else:
        fehler_beschreibung, konto = Kern_Buchung.int_from_string(dict_value, False, False, name)
        return (fehler_beschreibung, (konto, None))

def vf_format_konto(konto, kostenstelle):
    if kostenstelle:
        return u'{0}-{1}'.format (unicode(konto), unicode(kostenstelle))
    else:
        return unicode(konto)
