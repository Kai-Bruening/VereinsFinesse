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


class Kern_Buchung:
    """Räpresentiert den seitenunabhängigen Kern einer Buchung"""

    def __init__(self):
        self.datum = None
        self.buchungstext = None
        self.konto_soll = None
        self.konto_soll_name = None
        self.konto_haben = None
        self.konto_haben_name = None
        self.kostenstelle = None
        self.betrag_soll = None
        self.betrag_haben = None
        self.steuerfall = None
        self.steuer_betrag_soll = Decimal(0)
        self.steuer_betrag_haben = Decimal(0)
        self.rechnungsnummer = None
        self.belegnummer = None

    @property
    def konten_key_ohne_kostenstelle(self):
        """
        :rtype: list
       """
        # Vertauschte Konten müssen den gleichen Schlüssel ergeben.
        konto1 = self.konto_soll
        konto2 = self.konto_haben
        # Vertauschte Konten müssen den gleichen Schlüssel ergeben.
        if konto1 > konto2:
            temp = konto1
            konto1 = konto2
            konto2 = temp
        return konto1, konto2

    @property
    def konten_key(self):
        return self.konten_key_ohne_kostenstelle + (self.kostenstelle , )

    def kompatible_buchungen_key(self, mit_kostenstelle):
        """
        Erzeugt einen Schlüssel, der für untereinander kompatible Buchungen gleich ist.
        Buchungen sind kompatibel, wenn sie zwischen den gleichen zwei Konten mit dem gleichen Steuerfall und der
        gleichen Kostenstelle buchen.
         :rtype: list
        """
        if mit_kostenstelle:
            key = self.konten_key
        else:
            key = self.konten_key_ohne_kostenstelle
        steuercode = None
        if self.steuerfall:
            steuercode = self.steuerfall.code
        return key + (steuercode , )

    @property
    def is_null(self):
        # Buchungen im VF mit Betrag = 0 sind möglich und entstehen z.B. beim Löschen von Rechnungen.
        # Die Zuordnung der Konten auf Soll und Haben nach dem Vorzeichen ist dann nicht möglich.
        return self.betrag_soll == Decimal(0) and self.betrag_haben == Decimal(0)

    def buchung_mit_getauschten_konten(self):
        if self.steuer_betrag_haben != Decimal(0) or self.steuer_betrag_soll != Decimal(0):
            pass

        neue_buchung = copy.copy(self)
        neue_buchung.konto_soll = self.konto_haben
        neue_buchung.konto_soll_name = self.konto_haben_name
        neue_buchung.konto_haben = self.konto_soll
        neue_buchung.konto_haben_name = self.konto_soll_name
        neue_buchung.betrag_soll = -self.betrag_haben
        neue_buchung.betrag_haben = -self.betrag_soll
        neue_buchung.steuer_betrag_soll = -self.steuer_betrag_haben
        neue_buchung.steuer_betrag_haben = -self.steuer_betrag_soll

        return neue_buchung

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

    def matches_buchung(self, other_buchung):
        """
         :param other_buchung:Kern_Buchung
         :rtype: bool
         """

        if not Configuration.sind_steuerfaelle_aequivalent(self.steuerfall, other_buchung.steuerfall):
            return False

        if self.kostenstelle != other_buchung.kostenstelle:
            return False
        if self.konto_soll != other_buchung.konto_soll:
            return False
        if self.konto_haben != other_buchung.konto_haben:
            return False
        if self.betrag_soll != other_buchung.betrag_soll:
            return False
        if self.betrag_haben != other_buchung.betrag_haben:
            return False
        if self.steuer_betrag_soll != other_buchung.steuer_betrag_soll:
            return False
        if self.steuer_betrag_haben != other_buchung.steuer_betrag_haben:
            return False
        return True

    def ist_ein_konto_enthalten_in(self, konten_liste):
        return konten_liste.enthaelt_konto(self.konto_haben) or konten_liste.enthaelt_konto(self.konto_soll)

    def ist_storno_gegen(self, andere_buchung):
        if self.matches_konten_of_buchung(andere_buchung):
            # Wenn die Konten gleich sind, müssen die Beträge entgegengesetzt sein.
            if (andere_buchung.betrag_soll == -self.betrag_soll and
                        andere_buchung.betrag_haben == -self.betrag_haben and
                        andere_buchung.steuer_betrag_soll == -self.steuer_betrag_soll and
                        andere_buchung.steuer_betrag_haben == -self.steuer_betrag_haben):
                return True
        elif self.anti_matches_konten_of_buchung(andere_buchung):
            # Andernfalls müssen die Beträge bei vertauschten Konten gleich sein.
            if (andere_buchung.betrag_soll == self.betrag_haben and
                        andere_buchung.betrag_haben == self.betrag_soll and
                        andere_buchung.steuer_betrag_soll == self.steuer_betrag_haben and
                        andere_buchung.steuer_betrag_haben == self.steuer_betrag_soll):
                return True
        return False

    def fehler_beschreibung_fuer_export_nach_vf(self, konfiguration):
        """
        Überprüft ob diese Buchung zum VF exportiert werden kann und gibt eine Fehlerbeschreibung zurück falls nicht.
        Im Erfolgsfall ist das Ergbnis None.
        Nach der Umstellung auf explizite Kostenstellen im VF ist hier zur Zeit nichts zu überprüfen.
        """
        return None

    def subtract_betraege_von(self, andere_buchung):
        """
        """
        if andere_buchung.matches_konten_of_buchung(self):
            self.betrag_soll -= andere_buchung.betrag_soll
            self.betrag_haben -= andere_buchung.betrag_haben
            self.steuer_betrag_soll -= andere_buchung.steuer_betrag_soll
            self.steuer_betrag_haben -= andere_buchung.steuer_betrag_haben
        else:
            # TODO: unit test for this case
            assert andere_buchung.anti_matches_konten_of_buchung(self)
            self.betrag_soll += andere_buchung.betrag_haben
            self.betrag_haben += andere_buchung.betrag_soll
            self.steuer_betrag_soll += andere_buchung.steuer_betrag_haben
            self.steuer_betrag_haben += andere_buchung.steuer_betrag_soll

    def dict_for_export_to_vf(self, konfiguration):
        """
        :rtype: dict
        """

        # Note: fehlende Dict-Einträge werden automatisch als Leerstrings exportiert.
        result = {}
        result[u'Datum'] = self.datum.strftime('%d.%m.%Y')
        result[u'Buchungstext'] = self.buchungstext

        # Der Normalfall ist, das Habenkonto auf 'Konto' im VF abzubilden. Bei positivem Betrag wird dieses Konto
        # vom VF als Habenkonto angezeigt.
        konto_im_haben = True
        if self.steuerfall:
            # Der Bruttobetrag muss immer auf das Konto gebucht werden, der Nettobetrag auf das Gegenkonto.
            if abs (self.betrag_soll) > abs (self.betrag_haben):
                konto_im_haben = False

        # Notiz: früher haben wir Mitgliedskonten möglichst dem "Konto" zugeordnet, damit sie im Journal des VF
        # möglichst links stehen. Das bringt seit der Umstellung auf Soll- und Haben-Darstellung nichts mehr und
        # ist daher weg.

        if konto_im_haben:
            konto = self.konto_haben
            gegen_konto = self.konto_soll
            betrag = self.betrag_haben
        else:
            konto = self.konto_soll
            gegen_konto = self.konto_haben
            betrag = -self.betrag_soll

        # Note: fehlende Dict-Einträge werden automatisch als Leerstrings exportiert.
        result[u'Konto']        = self.konto_for_vf_export(konto, konfiguration)
        result[u'Gegenkonto']   = self.konto_for_vf_export(gegen_konto, konfiguration)
        if self.kostenstelle:
            result[u'Kostenstelle'] = unicode(konfiguration.vf_kostenstelle_from_kostenstelle(self.kostenstelle))
        result[u'Betrag']       = betrag

        if self.steuerfall:
            steuerkonto = konfiguration.steuer_configuration.vf_steuer_konto_for_steuerfall(self.steuerfall)
            if steuerkonto:
                result[u'Steuerkonto'] = steuerkonto
            result[u'Mwst'] = self.steuerfall.ust_satz

        return result

    def konto_for_vf_export(self, konto, konfiguration):
        return unicode(konfiguration.vf_konto_from_konto(konto))

    def dict_for_export_to_finesse(self, konfiguration):
        """
        :rtype: dict
        """

        # Note: fehlende Dict-Einträge werden automatisch als Leerstrings exportiert.
        result = {}
        result[u'Datum'] = self.datum.strftime('%d.%m.%Y')
        result[u'Buchungstext'] = self.buchungstext
        result[u'Konto Soll'] = self.konto_soll
        result[u'Konto Haben'] = self.konto_haben

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

        if self.kostenstelle:
            result[u'Kostenrechnungsobjekt 1'] = konfiguration.finesse_kostenstelle_from_kostenstelle(self.kostenstelle)
        if self.rechnungsnummer:
            result[u'Rechnungsnummer'] = self.rechnungsnummer

        # Die VF-Belegnummer gilt nur im Kontext einer Belegart, aber da Finesse nur Zahlen als Belegnummer akzeptiert,
        # kann die Belegart nicht ohne weiteres mit übertragen werden.
        if self.belegnummer:
            result[u'Belegnummer 1'] = self.belegnummer

        return result


int_string_expr = re.compile('\s*([0-9]{0,10})\s*$')

def int_from_string(s, is_empty_ok, map_zero_to_none, name):
    match = int_string_expr.match(s)
    if not match:
        return (u'{0} ({1}) nicht lesbar'.format(name, s), None)
    num_string = match.group(1)
    if len(num_string) > 0:
        result = int(match.group(1))
        if result == 0 and map_zero_to_none:
            return (None, None)
        return (None, result)
    if is_empty_ok:
        return (None, None)
    return (u'{0} ist leer'.format(name), None)
