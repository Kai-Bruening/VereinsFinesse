# -*- coding: utf-8 -*-

import yaml
from decimal import Decimal


def enum(**named_values):
    return type('Enum', (), named_values)


steuerart = enum(Keine=u'keine', Vorsteuer=u'vorsteuer', Umsatzsteuer=u'umsatzsteuer')


class Konfiguration:

    def __init__(self, config_dict):
        self.config_dict = config_dict

        if u'ignoriere_aenderung_der_kostenstelle' in config_dict:
            self.ignoriere_aenderung_der_kostenstelle = config_dict[u'ignoriere_aenderung_der_kostenstelle']
        else:
            self.ignoriere_aenderung_der_kostenstelle = False

        self.steuer_configuration = SteuerConfiguration(config_dict)

        self.ausgenommene_konten_vf_nach_finesse = self.read_optional_list_from_config(u'ausgenommene_konten_vf_nach_finesse')
        self.konten_finesse_nach_vf = self.read_optional_list_from_config(u'konten_finesse_nach_vf')
        self.ausgenommene_konten_finesse_nach_vf = self.read_optional_list_from_config(u'ausgenommene_konten_finesse_nach_vf')

        self.konten_nummern_vf_nach_abgleich = self.read_optional_dictionary_from_config(u'konten_nummern_vf_nach_abgleich')
        self.konten_nummern_abgleich_nach_vf = self.read_optional_dictionary_from_config(u'konten_nummern_abgleich_nach_vf')
        self.konten_nummern_finesse_nach_abgleich = self.read_optional_dictionary_from_config(u'konten_nummern_finesse_nach_abgleich')
        self.konten_nummern_abgleich_nach_finesse = self.read_optional_dictionary_from_config(u'konten_nummern_abgleich_nach_finesse')

        self.kostenstellen_vf_nach_abgleich = self.read_optional_dictionary_from_config(u'kostenstellen_vf_nach_abgleich')
        self.kostenstellen_abgleich_nach_vf = self.read_optional_dictionary_from_config(u'kostenstellen_abgleich_nach_vf')
        self.kostenstellen_finesse_nach_abgleich = self.read_optional_dictionary_from_config(u'kostenstellen_finesse_nach_abgleich')
        self.kostenstellen_abgleich_nach_finesse = self.read_optional_dictionary_from_config(u'kostenstellen_abgleich_nach_finesse')

        if u'logge_stornierte_buchungen' in config_dict:
            self.logge_stornierte_buchungen = config_dict[u'logge_stornierte_buchungen']
        else:
            self.logge_stornierte_buchungen = False

    def read_optional_list_from_config(self, key):
        # Empty elements in yaml end up as None in the dictionary (the importer can’t know whether
        # some empty element was supposed to be an array).
        list = None
        if key in self.config_dict:
            list = self.config_dict[key]
        return Kontenbereiche(list)

    def read_optional_dictionary_from_config(self, key):
        # Empty elements in yaml end up as None in the dictionary (the importer can’t know whether
        # some empty element was supposed to be an array).
        dict = {}
        if key in self.config_dict:
            dict = self.config_dict[key]
        return dict

    def konto_from_vf_konto(self, vf_konto):
        if vf_konto in self.konten_nummern_vf_nach_abgleich:
            return self.konten_nummern_vf_nach_abgleich[vf_konto]
        return vf_konto

    def vf_konto_from_konto(self, konto):
        if konto in self.konten_nummern_abgleich_nach_vf:
            return self.konten_nummern_abgleich_nach_vf[konto]
        return konto

    def konto_from_finesse_konto(self, finesse_konto):
        if finesse_konto in self.konten_nummern_finesse_nach_abgleich:
            return self.konten_nummern_finesse_nach_abgleich[finesse_konto]
        return finesse_konto

    def finesse_konto_from_konto(self, konto):
        if konto in self.konten_nummern_abgleich_nach_finesse:
            return self.konten_nummern_abgleich_nach_finesse[konto]
        return konto

    def kostenstelle_from_vf_kostenstelle(self, kostenstelle):
        if kostenstelle in self.kostenstellen_vf_nach_abgleich:
            return self.kostenstellen_vf_nach_abgleich[kostenstelle]
        return kostenstelle

    def vf_kostenstelle_from_kostenstelle(self, kostenstelle):
        if kostenstelle in self.kostenstellen_abgleich_nach_vf:
            return self.kostenstellen_abgleich_nach_vf[kostenstelle]
        return kostenstelle

    def kostenstelle_from_finesse_kostenstelle(self, kostenstelle):
        if kostenstelle in self.kostenstellen_finesse_nach_abgleich:
            return self.kostenstellen_finesse_nach_abgleich[kostenstelle]
        return kostenstelle

    def finesse_kostenstelle_from_kostenstelle(self, kostenstelle):
        if kostenstelle in self.kostenstellen_abgleich_nach_finesse:
            return self.kostenstellen_abgleich_nach_finesse[kostenstelle]
        return kostenstelle


class Steuerfall(yaml.YAMLObject):
    yaml_tag = u'!Steuerfall'

    def __setstate__(self, state_dict):
        self.code = state_dict['code']

        art = state_dict['art']
        if art == steuerart.Keine:
            self.art = steuerart.Keine
        elif art == steuerart.Vorsteuer:
            self.art = steuerart.Vorsteuer
        else:
            assert art == steuerart.Umsatzsteuer
            self.art = steuerart.Umsatzsteuer

        self.konto_finesse = None
        self.konto_vf = None

        # Belege beide Kontos mit dem Wert von 'konto' vor, dann korrigiere wie nötig.
        if 'konto' in state_dict:
            self.konto_finesse = state_dict['konto']
            self.konto_vf = state_dict['konto']
        if 'konto_finesse' in state_dict:
            self.konto_finesse = state_dict['konto_finesse']
        if 'konto_vf' in state_dict:
            self.konto_vf = state_dict['konto_vf']

        self.bezeichnung = state_dict['bezeichnung']
        if 'ust_satz' in state_dict:
            self.ust_satz = Decimal(state_dict['ust_satz'])
        else:
            self.ust_satz = None
        seite_text = state_dict['seite']
        assert seite_text == 'soll' or seite_text == 'haben'
        self.steuer_ins_haben = seite_text == 'haben'

    def matches_vf_steuerfall(self, vf_steuerfall):
        if not vf_steuerfall:
            return not self.ust_satz or self.ust_satz == Decimal(0)
        return (self.art == vf_steuerfall.art
                and self.ust_satz == vf_steuerfall.ust_satz)


def sind_steuerfaelle_aequivalent(steuerfall1, steuerfall2):
    if steuerfall1 == steuerfall2:
        return True
    # In Finesse haben wir auch Steuercodes mit -satz 0. Diese können im VF nicht unterschieden werden.
    #TODO: zur Vereinfachung einen Null-Steuersatz einführen?
    if not steuerfall1:
        return not steuerfall2.ust_satz or steuerfall2.ust_satz == Decimal(0)
    if not steuerfall2:
        return not steuerfall1.ust_satz or steuerfall1.ust_satz == Decimal(0)
    return (steuerfall1.art == steuerfall2.art
            and steuerfall1.ust_satz == steuerfall2.ust_satz)


class SteuerConfiguration:

    def __init__(self, config_dict):
        self.steuerfaelle = config_dict[u'steuerfaelle']
        # Nachschlagtabellen bauen.
        self.steuerfall_by_konto_finesse = {}
        self.steuerfall_by_konto_vf = {}
        self.steuerfall_by_code = {}
        for fall in self.steuerfaelle:
            if fall.konto_finesse not in self.steuerfall_by_konto_finesse:  # use first one of duplicates (like code 10)
                self.steuerfall_by_konto_finesse[fall.konto_finesse] = fall
            if fall.konto_vf and (fall.konto_vf not in self.steuerfall_by_konto_vf):
                self.steuerfall_by_konto_vf[fall.konto_vf] = fall
            self.steuerfall_by_code[fall.code] = fall

    def steuerfall_for_vf_steuerkonto_and_steuersatz(self, vf_konto, satz):
        for fall in self.steuerfaelle:
            if fall.konto_vf == vf_konto:
                if fall.ust_satz == satz:
                    return fall
                # Spezialfall für "freie Eingabe Vorsteuer"
                if satz == Decimal(0) and not fall.ust_satz:
                    return fall
        return None

    def steuerfall_for_finesse_steuercode(self, steuercode):
        if steuercode not in self.steuerfall_by_code:
            return None
        return self.steuerfall_by_code[steuercode]

    def vf_steuer_konto_for_steuerfall(self, steuerfall):
        return steuerfall.konto_vf


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
