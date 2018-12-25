# -*- coding: utf-8 -*-

import os.path
import sys
import argparse
import yaml
import VF_Buchung
import Finesse_Buchung
import csv
import UnicodeCSV
import codecs
import Configuration
from decimal import Decimal

vf_import_file_name = u'Zum Import in Vereinsflieger.csv'
finesse_import_file_name = u'Zum Import in Finesse.csv'
protokoll_file_name = u'Protokoll.txt'
fehler_file_name = u'Fehlerhafte Buchungen.csv'

csv.register_dialect('Vereinsflieger', delimiter=";", strict=True)


class MainController:
    """Steuert den Buchungstransfer zwischen Vereinsflieger und Finesse"""

    def __init__(self):
        self.finesse_buchungen = []

        # Alle Buchungen aus Finesse, die prinzipiell nach VF exportiert werden können einschließlich bereits
        # exportierter Buchungen. Dies sind alle Buchungen im Dialog, die nicht aus VF importiert wurden.
        # Da es zu jeder Journalnummer im Dialog mehrere Buchungen geben kann (für Skonto), ist jeder Eintrag ein
        # Dictionary mit Buchungen nach ihrem Kontenschlüssel.
        self.exportable_finesse_buchungen_by_finesse_journal_nr = {}

        # Alle Buchungen aus Finesse, die aus VF importiert wurden. Diese Buchungen können im Dialog oder in
        # Vereinsflieger-Import sein.
        self.finesse_buchungen_originally_imported_from_vf = []

        self.finesse_buchungen_for_export_by_konten_key = {}   # Für den Storno-Check

        self.vf_buchungen = []
        self.vf_buchungenImportedFromFinesse = {}
        self.vf_buchungenForExportToFinesse = []
        self.vf_buchungenForExportToFinesseByVFNr = {}
        self.vf_buchungenByNr = {}

        self.fehlerhafte_vf_buchungen = []
        self.fehlerhafte_finesse_buchungen = []

    def run(self):
        # argparse exits on error after printing a message - no need to modify this.
        self.parse_args()

        self.open_protokoll_file()

        try:
            self.delete_old_output_files()

            self.open_config()

            path = self.vf_export_path()
            if path:
                self.import_vf(path)
            path = self.finesse_export_path()
            if path:
                self.import_finesse(path)
            #self.raise_if_pending_errors()

            self.connectImportedVFBuchungen()
            self.connectImportedFinesseBuchungen()
            #self.raise_if_pending_errors()

            self.entferne_stornierte_finesse_buchungen()

            finesse_export_list = self.finesseBuchungenForExportToVF()
            vf_exportList = self.vfBuchungenForExportToFinesse()
            #self.raise_if_pending_errors()

            if len(finesse_export_list) > 0:
                f = open(vf_import_file_name, 'wb')
                self.exportFinesseBuchungenToVF(finesse_export_list, f)

            if len(vf_exportList) > 0:
                f = open(finesse_import_file_name , 'wb')
                self.exportVFBuchungenToFinesse(vf_exportList, f)

        except StopRun:
            self.protokoll_stream.writelines([u"Abbruch nach Fehlern.", os.linesep])

        except:
            self.protokoll_stream.writelines([u"Abbruch wegen unerwarteten Fehlers: {0}".format(sys.exc_info()), os.linesep])

        else:
            if self.has_fehlerhafte_buchungen:
                self.protokoll_stream.writelines([u"Datenaustausch beendet.", os.linesep])
                if len(self.fehlerhafte_vf_buchungen) > 0:
                    self.protokoll_stream.writelines([u"{0} Buchungen aus dem Vereinsflieger konnten nicht bearbeitet werden.".format(len(self.fehlerhafte_vf_buchungen)), os.linesep])
                if len(self.fehlerhafte_finesse_buchungen) > 0:
                    self.protokoll_stream.writelines([u"{0} Buchungen aus Finesse konnten nicht bearbeitet werden.".format(len(self.fehlerhafte_finesse_buchungen)), os.linesep])
                self.protokoll_stream.writelines([u"Siehe „{0}“ für Details.".format(fehler_file_name), os.linesep])
            else:
                self.protokoll_stream.writelines([u"Datenaustausch ohne Fehler beendet.", os.linesep])

            self.report_fehlerhafte_buchungen(fehler_file_name)

    def parse_args(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('--vf_export')
        parser.add_argument('--finesse_export')
        parser.add_argument('-c', '--config')
        self.parsed_args = parser.parse_args()

    def open_protokoll_file(self):
        f = open(protokoll_file_name, 'wb')

        # Mark the file as using utf-8
        bom = bytearray([239, 187, 191])    # the utf-8 byte order mark
        f.write(bom)

        self.protokoll_stream = codecs.getwriter("utf-8")(f)

    def delete_old_output_files(self):
        # Make sure we leave no old output behind.
        # os.remove() throws if the file does not exist, just continue in this case.
        try:
            os.remove(vf_import_file_name)
        except:
            pass
        try:
            os.remove(finesse_import_file_name)
        except:
            pass

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
            self.protokoll_stream.writelines([u"Fehler beim Lesen der Konfiguration von „{0}“: {1}".format(stream.name, error), os.linesep])
            raise StopRun()

    def is_buchung_exported_to_finesse(self, vf_buchung):
        return not vf_buchung.kern_buchung.ist_ein_konto_enthalten_in(self.konfiguration.ausgenommene_konten_vf_nach_finesse)

    def is_buchung_exported_to_vf(self, finesse_buchung):
        return (finesse_buchung.kern_buchung.ist_ein_konto_enthalten_in(self.konfiguration.konten_finesse_nach_vf)
        and not finesse_buchung.kern_buchung.ist_ein_konto_enthalten_in(self.konfiguration.ausgenommene_konten_finesse_nach_vf))

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
                self.protokoll_stream.writelines([u'Quellzeile {0} in {1} enthält unerwartete Daten {2}.'.format(reader.line_num, path, row_dict[u'<ÜBERHANG>']), os.linesep])
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

    def exportFinesseBuchungenToVF(self, finesse_buchungen, filehandle):
        writer = UnicodeCSV.UnicodeDictWriter(filehandle,
                                   VF_Buchung.VF_Buchung.fieldnames_for_export_to_vf(),
                                   encoding="windows-1252",
                                   restval='',
                                   delimiter=";",
                                   quoting=csv.QUOTE_MINIMAL,
                                   strict=True)
        writer.writeheader()
        for finesse_buchung in finesse_buchungen:
            writer.writerow(finesse_buchung.dict_for_export_to_vf)


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
                self.protokoll_stream.writelines([u'Quellzeile {0} in {1} enthält unerwartete Daten {2}.'.format(reader.line_num, path, row_dict[u'<ÜBERHANG>']), os.linesep])
                raise StopRun()

            # Ein spezieller Wert (der höchstmögliche in Finesse) für die VF-Nr markiert Buchung aus Finesse, die
            # komplett ignoriert werden sollen.
            if row_dict[u'Beleg 2'] == u'999999999':
                continue

            b = Finesse_Buchung.Finesse_Buchung(self.konfiguration)
            if not b.init_from_finesse(row_dict):
                self.fehlerhafte_finesse_buchungen.append(b)
                continue

            self.finesse_buchungen.append(b)    # used by unit tests only

            # Buchungen in Finesse, die bei einem früheren Abgleich aus dem Vereinsflieger übernommen wurden, müssen
            # hier wiedererkannt werden, um erneuten Export nach Finesse zu verhindern.
            if b.vf_nr:
                self.finesse_buchungen_originally_imported_from_vf.append(b)

            # Nur Buchungen aus dem "Dialog" in Finesse können in den Vereinsflieger übernommen werden, da nur sie
            # endgültig und eindeutig zu identifizieren sind.
            elif b.finesse_buchungs_journal == Finesse_Buchung.finesse_fournal_for_export_to_vf:
                if self.add_to_exportable_finesse_buchungen(b):
                    self.add_finesse_buchung_to_table_by_konten_key(b)
                    # Nur Buchungen für bestimmte Konten entsprechend der Konfiguration werden tatsächlich in den
                    # VF übernommen.
                    # if self.is_buchung_exported_to_vf(b):
                    #     self.add_to_buchungen_for_export_to_vf(b)

    def add_to_exportable_finesse_buchungen(self, finesse_buchung):
        # Mehrere Finesse-Buchungen im Dialog können die gleiche Nummer haben (wird für Skonto benutzt).
        # Deshalb ist jeder Eintrag ein Dictionary von Buchungen unter dem Kontenschlüssel.
        konten_key = finesse_buchung.kern_buchung.konten_key
        journalnummer = finesse_buchung.finesse_journalnummer
        if journalnummer in self.exportable_finesse_buchungen_by_finesse_journal_nr:
            buchung_by_konten_key = self.exportable_finesse_buchungen_by_finesse_journal_nr[journalnummer]
            # Buchungen mit derselben Nummer müssen sich im Kontenschlüssel unterscheiden, wie soll man sie sonst
            # auseinander halten?
            if konten_key in buchung_by_konten_key:
                # Die bereits vorhandene Buchung wird ebenfalls als fehlerhaft markiert…
                b2 = buchung_by_konten_key[konten_key]
                if not b2.fehler_beschreibung:
                    b2.fehler_beschreibung = u'Mehrere Buchungen aus Finesse mit einer Dialog-Journalnummer ({0}) und gleichen Konten'.format(
                        journalnummer)
                    self.fehlerhafte_finesse_buchungen.append(b2)

                finesse_buchung.fehler_beschreibung = u'Mehrere Buchungen aus Finesse mit einer Dialog-Journalnummer ({0}) und gleichen Konten'.format(
                    journalnummer)
                self.fehlerhafte_finesse_buchungen.append(finesse_buchung)
                return False
            # Neue Buchung zum Dictionary hinzufügen.
            buchung_by_konten_key[konten_key] = finesse_buchung
        else:
            # Dictionary mit einer Buchung beginnen.
            self.exportable_finesse_buchungen_by_finesse_journal_nr[journalnummer] = {konten_key: finesse_buchung}

        return True

    def remove_from_exportable_finesse_buchungen(self, finesse_buchung):
        journalnummer = finesse_buchung.finesse_journalnummer
        if journalnummer in self.exportable_finesse_buchungen_by_finesse_journal_nr:
            buchung_by_konten_key = self.exportable_finesse_buchungen_by_finesse_journal_nr[journalnummer]
            konten_key = finesse_buchung.kern_buchung.konten_key
            if konten_key in buchung_by_konten_key:
                del buchung_by_konten_key[konten_key]   # wird zum Erkennen von Stornos benutzt

    def add_finesse_buchung_to_table_by_konten_key(self, finesse_buchung):
        konten_key = finesse_buchung.kern_buchung.konten_key
        if konten_key in self.finesse_buchungen_for_export_by_konten_key:
            self.finesse_buchungen_for_export_by_konten_key[konten_key].append(finesse_buchung)
        else:
            self.finesse_buchungen_for_export_by_konten_key[konten_key] = [finesse_buchung]

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
            for finesse_dict in vfBuchung.dicts_for_export_to_finesse:
                writer.writerow(finesse_dict)

    def connectImportedVFBuchungen(self):
        for vf_buchung in self.vf_buchungenImportedFromFinesse.itervalues():
            vf_fehler_beschreibung = None
            finesse_fehler_beschreibung = None
            original_finesse_buchung = None

            finesse_journalnummer = vf_buchung.finesse_journalnummer
            if not finesse_journalnummer in self.exportable_finesse_buchungen_by_finesse_journal_nr:
                vf_fehler_beschreibung = u'Originale Finesse-Buchung (Dialog: {0}) nicht gefunden'.format(finesse_journalnummer)
            else:
                original_finesse_buchung_by_konten_key = self.exportable_finesse_buchungen_by_finesse_journal_nr[finesse_journalnummer]
                konten_key = vf_buchung.kern_buchung.konten_key
                if not konten_key in original_finesse_buchung_by_konten_key:
                    vf_fehler_beschreibung = u'Originale Finesse-Buchung mit passenden Konten ({0}, {1}, {2}) nicht unter Dialog {3} gefunden'.format(
                        konten_key[0], konten_key[1], konten_key[2], finesse_journalnummer)
                else:
                    original_finesse_buchung = original_finesse_buchung_by_konten_key[konten_key]
                    if original_finesse_buchung.kopierte_vf_buchung:
                        vf_fehler_beschreibung = u'Mehrere VF-Buchungen zu einer Journalnummer in Finesse (Dialog: {0})'.format(finesse_journalnummer)
                        finesse_fehler_beschreibung = u'Mehrere VF-Buchungen zu dieser Finesse-Buchung gefunden'
                    else:
                        # Buchungen in Finesse dürfen sich zwischen Synchronisierungen nicht ändern, und die Kopie
                        # im VF darf auch nicht geändert werden.
                        if not vf_buchung.validate_for_original_finesse_buchung(original_finesse_buchung):
                            vf_buchung.validate_for_original_finesse_buchung(original_finesse_buchung)  # repeated for debugging
                            vf_fehler_beschreibung = u'Importierte VF-Buchung weicht von originaler Finesse-Buchung (Dialog: {0}) ab'.format(finesse_journalnummer)
                            finesse_fehler_beschreibung = u'Originale Finesse-Buchung weicht von importierte VF-Buchung ab'
                        else:
                            vf_buchung.original_finesse_buchung = original_finesse_buchung
                            original_finesse_buchung.kopierte_vf_buchung = vf_buchung

            if vf_fehler_beschreibung:
                vf_buchung.fehler_beschreibung = vf_fehler_beschreibung
                self.fehlerhafte_vf_buchungen.append(vf_buchung)
            if finesse_fehler_beschreibung:
                original_finesse_buchung.fehler_beschreibung = finesse_fehler_beschreibung
                self.fehlerhafte_finesse_buchungen.append(original_finesse_buchung)

    def finesseBuchungenForExportToVF(self):
        """
        :rtype: list
        """
        result = []
        for buchung_by_konten_key in self.exportable_finesse_buchungen_by_finesse_journal_nr.itervalues():
            # Mehrere Buchungen zu einer Journalnummer müssen für die Unit-Tests in einer definierten Reihenfolge
            # exportiert werden.
            sub_result = []
            for finesse_buchung in buchung_by_konten_key.itervalues():
                if not finesse_buchung.kopierte_vf_buchung and not finesse_buchung.fehler_beschreibung:
                    if self.is_buchung_exported_to_vf(finesse_buchung):
                        if finesse_buchung.ist_valide_fuer_export_nach_vf:
                            sub_result.append(finesse_buchung)
                        else:
                            self.fehlerhafte_finesse_buchungen.append(finesse_buchung)
            sub_result.sort(key=lambda b:b.kern_buchung.konten_key)
            result += sub_result
        return result

    def connectImportedFinesseBuchungen(self):
        for finesse_buchung in self.finesse_buchungen_originally_imported_from_vf:
            original_vf_buchung = self.ensure_original_vf_buchung_for_imported_finesse_buchung(finesse_buchung)
            original_vf_buchung.connect_kopierte_finesse_buchung(finesse_buchung)

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
        for key, storno_group in self.finesse_buchungen_for_export_by_konten_key.items():
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
                            if self.konfiguration.logge_stornierte_buchungen:
                                self.protokoll_stream.writelines([u'Finesse Buchung {0}:{1} storniert gegen Buchung {2}:{3}.'.format(
                                    b.finesse_buchungs_journal, b.finesse_journalnummer,
                                    storno_partner.finesse_buchungs_journal, storno_partner.finesse_journalnummer),
                                    os.linesep])

                            # Entferne das stornierte Buchungspaar aus Export- und Kandidatenliste.
                            self.remove_from_exportable_finesse_buchungen(b)
                            self.remove_from_exportable_finesse_buchungen(storno_partner)
                            del storno_group[index]
                            storno_group.remove(storno_partner)
                            index -= 2
                    index += 1

    def vfBuchungenForExportToFinesse(self):
        """
        :rtype: list
        """
        return self.vf_buchungenForExportToFinesse;
        # result = []
        # for vf_buchung in self.vf_buchungenForExportToFinesse:
        #     finesse_buchungen = vf_buchung.finesse_buchungen_from_vf_buchung()
        #     if finesse_buchungen != None:
        #         result += finesse_buchungen
        #     else:
        #         self.fehlerhafte_vf_buchungen.append(vf_buchung)
        #
        # return result

    @property
    def has_fehlerhafte_buchungen(self):
        return len(self.fehlerhafte_vf_buchungen) > 0 or len(self.fehlerhafte_finesse_buchungen) > 0

    def report_fehlerhafte_buchungen(self, path):
        if self.has_fehlerhafte_buchungen:
            f = open(path, 'wb')

            # Mark the file as using utf-8
            bom = bytearray([239, 187, 191])    # the utf-8 byte order mark
            f.write(bom)
            f_utf8 = codecs.getwriter("utf-8")(f)

            if len(self.fehlerhafte_vf_buchungen) > 0:
                f_utf8.writelines([u"Folgende Buchungen aus dem Vereinsflieger können nicht verarbeitet werden:", os.linesep])
                self.write_fehlerhafte_buchungen(self.fehlerhafte_vf_buchungen, self.vf_export_fieldnames, f)
                f_utf8.writelines([os.linesep])

            if len(self.fehlerhafte_finesse_buchungen) > 0:
                f_utf8.write(u"Folgende Buchungen aus Finesse können nicht verarbeitet werden:")
                self.write_fehlerhafte_buchungen(self.fehlerhafte_finesse_buchungen, self.finesse_export_fieldnames, f)
                f_utf8.write(u"")

            f.close()
        else:
            try:
                os.remove(path)
            except:
                pass

    def write_fehlerhafte_buchungen(self, buchungen, fieldnames, filehandle):
        fieldnames.insert(0, u'Fehler')
        writer = UnicodeCSV.UnicodeDictWriter(filehandle,
                                   fieldnames,
                                   encoding = "utf-8",
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
