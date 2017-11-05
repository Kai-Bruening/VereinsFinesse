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

    def check_kostenstelle(self, konfiguration):
        """
        :param konfiguration: Configuration.Konfiguration
        """
        assert konfiguration

        if (not konfiguration.konten_mit_kostenstelle.enthaelt_konto(self.konto_soll)
           and not konfiguration.konten_mit_kostenstelle.enthaelt_konto(self.konto_haben)):
            self.kostenstelle = None

    # def tausche_konten(self):
    #     if self.steuer_betrag_haben != Decimal(0) or self.steuer_betrag_soll != Decimal(0):
    #         pass
    #
    #     temp_konto = self.konto_soll
    #     self.konto_soll = self.konto_haben
    #     self.konto_haben = temp_konto
    #
    #     temp_betrag = self.betrag_soll
    #     self.betrag_soll = -self.betrag_haben
    #     self.betrag_haben = -temp_betrag
    #
    #     temp_betrag = self.steuer_betrag_soll
    #     self.steuer_betrag_soll = -self.steuer_betrag_haben
    #     self.steuer_betrag_haben = -temp_betrag

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

    def dict_for_export_to_vf(self, konfiguration):
        """
        :rtype: dict
        """

        # Note: fehlende Dict-Einträge werden automatisch als Leerstrings exportiert.
        result = {}
        result[u'Datum'] = self.datum
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
        result[u'Konto']      = self.konto_for_vf_export(konto, konfiguration)
        result[u'Gegenkonto'] = self.konto_for_vf_export(gegen_konto, konfiguration)
        result[u'Betrag']     = betrag

        if self.steuerfall:
            result[u'Steuerkonto'] = konfiguration.steuer_configuration.vf_steuer_konto_for_steuerfall(self.steuerfall)
            result[u'Mwst'] = self.steuerfall.ust_satz

        return result

    def konto_for_vf_export(self, konto, konfiguration):
        kostenstelle = self.kostenstelle
        if not konfiguration.konten_mit_kostenstelle.enthaelt_konto(konto):
            kostenstelle = None
        return VF_Buchung.vf_format_konto(konfiguration.vf_konto_from_konto(konto), kostenstelle)
