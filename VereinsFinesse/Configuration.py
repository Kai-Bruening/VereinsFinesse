# -*- coding: utf-8 -*-

import yaml
from decimal import *


class Steuerfall(yaml.YAMLObject):
    yaml_tag = u'!Steuerfall'

    def __setstate__(self, state_dict):
        self.code = state_dict['code']
        self.konto_finesse = state_dict['konto_finesse']
        self.bezeichnung = state_dict['bezeichnung']
        if 'ust_satz' in state_dict:
            self.ust_satz = Decimal(state_dict['ust_satz'])
        else:
            self.ust_satz = None
        seite_text = state_dict['seite']
        assert seite_text == 'soll' or seite_text == 'haben'
        self.steuer_ins_haben = seite_text == 'haben'


class SteuerConfiguration:

    def __init__(self, config_dict):
        self.vf_vorsteuer_konto = config_dict[u'vf_vorsteuer_konto']
        self.vf_umsatzsteuer_konto = config_dict[u'vf_umsatzsteuer_konto']
        self.steuerfaelle = config_dict[u'steuerfaelle']
        # Nachschlagtabellen bauen.
        self.steuerfall_by_konto_finesse = {}
        self.steuerfall_by_code = {}
        for fall in self.steuerfaelle:
            if fall.konto_finesse not in self.steuerfall_by_konto_finesse:  # use first one of duplicates (like code 10)
                self.steuerfall_by_konto_finesse[fall.konto_finesse] = fall
            self.steuerfall_by_code[fall.code] = fall

    def steuerfall_for_vf_steuerkonto_and_steuersatz(self, konto, satz):
        if konto == self.vf_vorsteuer_konto:
            for fall in self.steuerfaelle:
                if not fall.steuer_ins_haben and fall.ust_satz == satz:
                    return fall
            return None
        elif konto == self.vf_umsatzsteuer_konto:
            for fall in self.steuerfaelle:
                if fall.steuer_ins_haben and fall.ust_satz == satz:
                    return fall
            return None
        elif konto in self.steuerfall_by_konto_finesse:
            return self.steuerfall_by_konto_finesse[konto]
        else:
            return None

    def steuerfall_for_finesse_steuercode(self, steuercode):
        if steuercode not in self.steuerfall_by_code:
            return None
        return self.steuerfall_by_code[steuercode]


class Kontenbereich(yaml.YAMLObject):
    yaml_tag = u'!Kontenbereich'

    def __setstate__(self, state_dict):
        self.start_konto = int(state_dict['start'])
        self.end_konto = int(state_dict['ende'])
        assert self.end_konto >= self.start_konto

    def enthaelt_konto(self, konto):
        return self.start_konto <= konto <= self.end_konto


class Kontenbereiche:

    def __init__(self, value):
        # Empty elements in yaml end up as None in the dictionary (the importer can’t know whether
        # some empty element was supposed to be an array).
        # Map both missing and empty case to empty array.
        if value:
            self.bereiche = value
        else:
            self.bereiche = []

    def enthaelt_konto(self, konto):
        for konto_bereich in self.bereiche:
            if konto_bereich.enthaelt_konto(konto):
                return True
        return False
