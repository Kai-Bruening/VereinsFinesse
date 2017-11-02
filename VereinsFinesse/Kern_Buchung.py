# -*- coding: utf-8 -*-

import string
import copy
import re
import math
import decimal
from decimal import Decimal
import Configuration
import CheckDigit


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
        self.steuer_konto = None
        self.steuer_konto_name = None
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
