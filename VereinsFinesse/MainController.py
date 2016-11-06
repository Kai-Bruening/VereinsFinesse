# -*- coding: utf-8 -*-

import os.path
import sys
import argparse
import yaml
import VF_Buchung
import Finesse_Buchung
import csv
import UnicodeCSV
import Configuration
from decimal import Decimal

csv.register_dialect('Vereinsflieger', delimiter=";", strict=True)


class MainController:
    """Steuert den Buchungstransfer zwischen Vereinsflieger und Finesse"""

    def __init__(self):
        self.finesse_buchungen = []
        self.finesse_buchungen_originally_imported_from_vf = []
        self.finesse_buchungen_for_export_to_vf_by_finesse_fournal_nr = {}
        self.finesse_buchungen_by_konten_key = {}   # Für den Storno-Check

        self.vf_buchungen = []
        self.vf_buchungenImportedFromFinesse = {}
        self.vf_buchungenForExportToFinesse = []
        self.vf_buchungenForExportToFinesseByVFNr = {}
        self.vf_buchungenByNr = {}

        self.fehlerhafte_vf_buchungen = []
        self.fehlerhafte_finesse_buchungen = []

    @property
    def has_fehlerhafte_buchungen(self):
        return len(self.fehlerhafte_vf_buchungen) > 0 or len(self.fehlerhafte_finesse_buchungen) > 0

    def run(self):
        # argparse exits on error after printing a message - no need to modify this.
        self.parse_args()

        try:
            self.open_config()

            path = self.vf_export_path()
            if path:
                self.import_vf(path)
            path = self.finesse_export_path()
            if path:
                self.import_finesse(path)
            self.raise_if_pending_errors()

            self.connectImportedVFBuchungen()
            self.connectImportedFinesseBuchungen()
            self.raise_if_pending_errors()

            self.entferne_stornierte_finesse_buchungen()

            finesse_export_list = self.finesseBuchungenForExportToVF()
            vf_exportList = self.vfBuchungenForExportToFinesse()
            self.raise_if_pending_errors()

            if len(finesse_export_list) > 0:
                # (head, tail) = os.path.split(self.parsed_args.vf_path)
                # vf_ExportPath = os.path.join(head, u'Zum Import in Vereinsflieger.csv')
                vf_exportpath = u'Zum Import in Vereinsflieger.csv'
                f = open(vf_exportpath, 'wb')
                self.exportFinesseBuchungenToVF(finesse_export_list, f)

            if len(vf_exportList) > 0:
                # (head, tail) = os.path.split(self.parsed_args.finesse_path)
                # finesse_ExportPath = os.path.join(head, u'Zum Import in Finesse.csv')
                finesse_exportpath = u'Zum Import in Finesse.csv'
                f = open(finesse_exportpath , 'wb')
                self.exportVFBuchungenToFinesse(vf_exportList, f)

        except StopRun:
            self.report_errors()
            print u"Abbruch nach Fehlern."

        except:
            print u"Abbruch wegen unerwarteten Fehlers:",  sys.exc_info()[0]

        else:
            print u"Datenaustausch erfolgreich beendet."

    def parse_args(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('--vf_export')
        parser.add_argument('--finesse_export')
        parser.add_argument('-c', '--config')
        self.parsed_args = parser.parse_args()

    def open_config(self):
        # Zur Zeit muss der Konfigurationspfad als Parameter angegeben werden.
        # TODO: implement default behavior
        config_path = self.parsed_args.config
        f = open(config_path , 'rb')
        self.read_config(f)

    def read_config(self, stream):
        try:
            config_dict = yaml.load(stream)
            self.konfiguration = Configuration.Konfiguration(config_dict)
        except yaml.parser.ParserError as error:
            print u"Fehler beim Lesen der Konfiguration von „{0}“:".format(stream.name), error
            raise StopRun()

    def is_buchung_exported_to_finesse(self, buchung):
        return (not self.konfiguration.ausgenommene_konten_vf_nach_finesse.enthaelt_konto(buchung.konto)
                and not self.konfiguration.ausgenommene_konten_vf_nach_finesse.enthaelt_konto(buchung.gegen_konto))

    def is_buchung_exported_to_vf(self, finesse_buchung):
        return (self.konfiguration.konten_finesse_nach_vf.enthaelt_konto(finesse_buchung.konto_haben)
                or self.konfiguration.konten_finesse_nach_vf.enthaelt_konto(finesse_buchung.konto_soll))

    def vf_export_path(self):
        vf_path = self.parsed_args.vf_export
        # if not vf_path:
        #     vf_path = u'buchungsexport.csv'
        return vf_path

    def finesse_export_path(self):
        finesse_path = self.parsed_args.finesse_export
        # if not finesse_path :
        #     finesse_path = u'F0BUS001.CSV'
        return finesse_path

    def import_vf(self, path):
        """
        """
        filehandle = open(path, 'rb')
        reader = UnicodeCSV.UnicodeDictReader(filehandle,
                                               encoding="windows-1252",
                                               restkey=u'<ÜBERHANG>',
                                               delimiter=";",
                                               strict=True)
        self.vf_export_fieldnames = reader.fieldnames
        #TODO: validate fieldnames?

        for row_dict in reader:
            if u'<ÜBERHANG>' in row_dict:
                print u'Quellzeile {0} in {1} enthält unerwartete Daten {2}.'.format(reader.line_num, path, row_dict[u'<ÜBERHANG>'])
                raise StopRun()

            b = VF_Buchung.VF_Buchung(self.konfiguration)
            if not b.init_from_vf(row_dict):
                self.fehlerhafte_vf_buchungen.append(b)
                continue

            # Jetzt zwischen Buchungen unterscheiden, die ursprünglich von Finesse importiert wurden, und solchen,
            # die im Vereinsflieger entstanden sind.
            is_import_from_finesse = b.vf_belegart == VF_Buchung.vf_belegart_for_import_from_finesse
            if is_import_from_finesse:
                buchungsdict = self.vf_buchungenImportedFromFinesse
            else:
                # Überspringe Buchungen, die nicht nach Finesse exportiert werden sollen.
                if not self.is_buchung_exported_to_finesse(b):
                    continue
                buchungsdict = self.vf_buchungenForExportToFinesseByVFNr

            if b.vf_nr in buchungsdict: # keine Split-Buchungen im VF
                b.fehler_beschreibung = u'Mehrere Buchungen im VF mit laufender Nr {0}'.format(b.vf_nr)
                self.fehlerhafte_vf_buchungen.append(b)
                continue

            buchungsdict[b.vf_nr] = b

            if not is_import_from_finesse:
                self.vf_buchungenForExportToFinesse.append(b)

            self.vf_buchungen.append(b) # alle importierten Buchungen werden hier gesammelt
            self.vf_buchungenByNr[b.vf_nr] = b

    def exportFinesseBuchungenToVF(self, vf_buchungen, filehandle):
        writer = UnicodeCSV.UnicodeDictWriter(filehandle,
                                   VF_Buchung.VF_Buchung.fieldnames_for_export_to_vf(),
                                   encoding="windows-1252",
                                   restval='',
                                   delimiter=";",
                                   quoting=csv.QUOTE_MINIMAL,
                                   strict=True)
        writer.writeheader()
        for vf_buchung in vf_buchungen:
            writer.writerow(vf_buchung.dict_for_export_to_vf)


    def import_finesse(self, path):
        """ """
        filehandle = open(path, 'rb')
        reader = UnicodeCSV.UnicodeDictReader(filehandle,
                                   encoding="windows-1252",
                                   restkey=u'<ÜBERHANG>',
                                   delimiter=";",
                                   strict=False)
        self.finesse_export_fieldnames = reader.fieldnames
        #TODO: validate fieldnames?

        for row_dict in reader:
            if u'<ÜBERHANG>' in row_dict:
                print u'Quellzeile {0} in {1} enthält unerwartete Daten {2}.'.format(reader.line_num, path, row_dict[u'<ÜBERHANG>'])
                raise StopRun()

            b = Finesse_Buchung.Finesse_Buchung(self.konfiguration)
            if not b.init_from_finesse(row_dict):
                self.fehlerhafte_finesse_buchungen.append(b)
                continue

            self.finesse_buchungen.append(b)    # used by unit tests only

            # Buchungen in Finesse, die bei einem früheren Abgleich aus dem Vereinsflieger übernommen wurden, müssen
            # hier wiedererkannt werden, um erneuten Export nach Finesse zu verhindern.
            if b.vf_nr:
                self.finesse_buchungen_originally_imported_from_vf.append(b)

            # Nur Buchungen auf Mitgliederkonten werden von Finesse in den Vereinsflieger übernommen (um die Salden
            # auf den Mitgliederkonten parallel zu halten).
            elif (b.finesse_buchungs_journal == Finesse_Buchung.finesse_fournal_for_export_to_vf
                  and self.is_buchung_exported_to_vf(b)):
                self.add_finesse_buchung_to_table_by_konten_key(b)
                # Storno-Check
                #if not self.is_finesse_buchung_storno(b):
                if b.finesse_journalnummer in self.finesse_buchungen_for_export_to_vf_by_finesse_fournal_nr:
                    b.fehler_beschreibung = u'Mitgliederbuchung aus Finesse mit nicht-eindeutiger Journalnummer ({0})'.format(b.finesse_journalnummer)
                    self.fehlerhafte_finesse_buchungen.append(b)
                else:
                    self.finesse_buchungen_for_export_to_vf_by_finesse_fournal_nr[b.finesse_journalnummer] = b

    def add_finesse_buchung_to_table_by_konten_key(self, finesse_buchung):
        konten_key = finesse_buchung.konten_key
        if konten_key in self.finesse_buchungen_by_konten_key:
            self.finesse_buchungen_by_konten_key[konten_key].append(finesse_buchung)
        else:
            self.finesse_buchungen_by_konten_key[konten_key] = [finesse_buchung]

    def exportVFBuchungenToFinesse(self, vfBuchungen, filehandle):
        writer = UnicodeCSV.UnicodeDictWriter(filehandle,
                                   Finesse_Buchung.Finesse_Buchung.fieldnames_for_export_to_finesse(),
                                   encoding="utf-8",
                                   restval='',
                                   delimiter=";",
                                   quoting=csv.QUOTE_MINIMAL,
                                   strict=True)
        writer.writeheader()
        for vfBuchung in vfBuchungen:
            writer.writerow(vfBuchung.dict_for_export_to_finesse)

    def connectImportedVFBuchungen(self):
        for vf_buchung in self.vf_buchungenImportedFromFinesse.itervalues():
            fehler_beschreibung = None
            finesse_journalnummer = vf_buchung.finesse_journalnummer
            if not finesse_journalnummer in self.finesse_buchungen_for_export_to_vf_by_finesse_fournal_nr:
                fehler_beschreibung = u'Originale Finesse-Buchung (Dialog: {0}) nicht gefunden'.format(finesse_journalnummer)
            else:
                original_finesse_buchung = self.finesse_buchungen_for_export_to_vf_by_finesse_fournal_nr[finesse_journalnummer]
                if original_finesse_buchung.kopierte_vf_buchung:
                    fehler_beschreibung = u'Mehrere VF-Buchungen zu einer Journalnummer in Finesse (Dialog: {0})'.format(finesse_journalnummer)
                else:
                    # Buchungen in Finesse dürfen sich zwischen Synchronisierungen nicht ändern, und die Kopie
                    # im VF darf auch nicht geändert werden.
                    if not vf_buchung.validate_for_original_finesse_buchung(original_finesse_buchung):
                        vf_buchung.validate_for_original_finesse_buchung(original_finesse_buchung)  # repeated for debugging
                        fehler_beschreibung = u'Importierte VF-Buchung weicht von originaler Finesse-Buchung (Dialog: {0}) ab'.format(finesse_journalnummer)
                    else:
                        vf_buchung.original_finesse_buchung = original_finesse_buchung
                        original_finesse_buchung.kopierte_vf_buchung = vf_buchung

            if fehler_beschreibung:
                vf_buchung.fehler_beschreibung = fehler_beschreibung
                self.fehlerhafte_vf_buchungen.append(vf_buchung)

    def finesseBuchungenForExportToVF(self):
        """
        :rtype: list
        """
        result = []
        for finesse_buchung in self.finesse_buchungen_for_export_to_vf_by_finesse_fournal_nr.itervalues():
            if not finesse_buchung.kopierte_vf_buchung:
                vf_buchung = finesse_buchung.vf_buchung_for_export()
                if vf_buchung:
                    result.append(vf_buchung)
                else:
                    self.fehlerhafte_finesse_buchungen.append(finesse_buchung)
        return result

    def connectImportedFinesseBuchungen(self):
        for finesse_buchung in self.finesse_buchungen_originally_imported_from_vf:
            fehler_beschreibung = None
            original_vf_buchung = self.ensure_original_vf_buchung_for_imported_finesse_buchung(finesse_buchung)
            # Buchungen im VF können jederzeit vom Betrag her geändert werden, aber die Konten und andere
            # Daten müssen bleiben.
            if not finesse_buchung.validate_for_original_vf_buchung(original_vf_buchung):
                finesse_buchung.validate_for_original_vf_buchung(original_vf_buchung)   # repeated for debugging
                fehler_beschreibung = u'Importierte Finesse-Buchung weicht von originaler VF-Buchung ({0}) ab'.format(
                    original_vf_buchung.vf_nr)
            else:
                # Buchungen im VF können geändert werden, deshalb kann es mehrere Buchung in Finesse für
                # eine einzige VF-Buchung geben.
                finesse_buchung.original_vf_buchung = original_vf_buchung
                if original_vf_buchung.kopierte_finesse_buchungen:
                    original_vf_buchung.kopierte_finesse_buchungen.append(finesse_buchung)
                    original_vf_buchung.kopierte_finesse_buchungen.sort(key = lambda x: x.finesse_journalnummer)
                else:
                    original_vf_buchung.kopierte_finesse_buchungen = [finesse_buchung]

            if fehler_beschreibung:
                finesse_buchung.fehler_beschreibung = fehler_beschreibung
                self.fehlerhafte_finesse_buchungen.append(finesse_buchung)

    def ensure_original_vf_buchung_for_imported_finesse_buchung(self, finesse_buchung):
        vf_nr = finesse_buchung.vf_nr
        if vf_nr in self.vf_buchungenForExportToFinesseByVFNr:
            return self.vf_buchungenForExportToFinesseByVFNr[vf_nr]
        # Die Buchung fehlt in der VF-Liste, muss also im VF gelöscht worden sein. Als Platzhalter erzeuge ich eine
        # Kopie der Finesse-Buchung mit Nullbeträgen.
        vf_buchung = finesse_buchung.create_placeholder_for_deleted_vf_buchung()
        self.vf_buchungenForExportToFinesse.append(vf_buchung )
        self.vf_buchungenForExportToFinesseByVFNr[vf_nr] = vf_buchung
        self.vf_buchungen.append(vf_buchung ) # alle importierten Buchungen werden hier gesammelt
        self.vf_buchungenByNr[vf_nr] = vf_buchung
        return vf_buchung

    def entferne_stornierte_finesse_buchungen(self):
        for key, storno_group in self.finesse_buchungen_by_konten_key.items():
            index = 0
            while index < len(storno_group):
                b = storno_group[index]
                if b.kopierte_vf_buchung:
                    # Buchungen, die schon im Vereinsflieger sind, können nicht mehr während der Übertragung storniert
                    # werden.
                    del storno_group[index]
                else:
                    if index > 0:
                        # Suche nach Stornopartner in den vorher importierten Buchungen.
                        storno_partner = b.lookup_storno_partner(storno_group[0:index])
                        if storno_partner:
                            # Entferne das stornierte Buchungspaar aus Export- und Kandidatenliste.
                            del self.finesse_buchungen_for_export_to_vf_by_finesse_fournal_nr[
                                b.finesse_journalnummer]
                            del self.finesse_buchungen_for_export_to_vf_by_finesse_fournal_nr[
                                storno_partner.finesse_journalnummer]
                            del storno_group[index]
                            storno_group.remove(storno_partner)
                            index -= 2
                    index += 1

    def vfBuchungenForExportToFinesse(self):
        """
        :rtype: list
        """
        result = []
        for vf_buchung in self.vf_buchungenForExportToFinesse:
            finesseBuchung = vf_buchung.finesse_buchung_from_vf_buchung()
            if finesseBuchung:
                # Finesse protestiert bei Buchung mit Betrag 0, was irgendwie verständlich ist.
                if finesseBuchung.betrag_soll != Decimal(0) and finesseBuchung.betrag_haben != Decimal(0):
                    result.append(finesseBuchung)
            else:
                self.fehlerhafte_vf_buchungen.append(vf_buchung)

        if len(self.fehlerhafte_vf_buchungen) > 0:
            raise StopRun()

        return result

    def raise_if_pending_errors(self):
       if len(self.fehlerhafte_vf_buchungen) > 0 or len(self.fehlerhafte_finesse_buchungen) > 0:
            raise StopRun()

    def report_errors(self):
        if len(self.fehlerhafte_vf_buchungen) > 0:
            print u"Folgende Buchungen aus dem Vereinsflieger können nicht verarbeitet werden:"
            self.write_fehlerhafte_buchungen(self.fehlerhafte_vf_buchungen, self.vf_export_fieldnames)
            print u""

        if len(self.fehlerhafte_finesse_buchungen) > 0:
            print u"Folgende Buchungen aus Finesse können nicht verarbeitet werden:"
            self.write_fehlerhafte_buchungen(self.fehlerhafte_finesse_buchungen, self.finesse_export_fieldnames)
            print u""

    def write_fehlerhafte_buchungen(self, buchungen, fieldnames):
        fieldnames.insert(0, u'Fehler')
        writer = UnicodeCSV.UnicodeDictWriter(sys.stdout,
                                   fieldnames,
                                   encoding = None,
                                   lineterminator=os.linesep,
                                   restval='',
                                   delimiter=";",
                                   quoting=csv.QUOTE_MINIMAL,
                                   strict=True)
        writer.writeheader()
        for b in buchungen:
            values = b.source_values
            values[u'Fehler'] = b.fehler_beschreibung
            writer.writerow(values)


class StopRun(Exception):
    pass

if __name__ == "__main__":
    mainController = MainController()
    mainController.run()
