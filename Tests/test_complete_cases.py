# -*- coding: utf-8 -*-

import unittest
import VereinsFinesse.MainController
import sys
import os
import tempfile
import filecmp


class CompleteTestCases (unittest.TestCase):

    def test_1(self):
        self.do_test_in_directory(u'Test 1')

    def test_umsatzsteuer_nach_finesse(self):
        # Übertrag von VF Buchungen mit Umsatzsteuer nach Finesse.
        # Die erste Buchung ist eine normale Belastung, die zweite storniert diese Belastung.
        self.do_test_in_directory(u'Umsatzsteuer nach Finesse')

    def test_fluggutschrift(self):
        # Übertrag der Gutschrift eines Fluges auf ein Mitgliedskonto. In diesem Fall geht die Steuer auf das
        # Vorsteuerkonto, was wahrscheinlich falsch ist, aber rechnerisch funtkioniert.
        self.do_test_in_directory(u'Fluggutschrift')

    def test_geloeschte_buchung_im_vf(self):
        # Testet das Erzeugen einer Stornobuchung für Finesse, nachdem eine bereits nach Finesse übetragene
        # Buchung im VF gelöscht wurde.
        self.do_test_in_directory(u'Gelöschte Buchung im VF')

    def test_brutto_netto_auswahl(self):
        # Testet die korrekte Zuordnung von Brutto und Nettobeträgen auf die Konten im Export von VF.
        self.do_test_in_directory(u'BruttoNettoAuswahl')

    def test_storno_in_finesse(self):
        # Wenn eine Buchung in Finesse storniert wird, bevor sie in VF übertragen ist, darf sie nicht
        # mehr nach VF übertragen werden. So können z.B. Buchungen mit falschem Konto oder Kostenstelle
        # storniert werden, ohne dass das falsche Konto im VF angelegt werden muss.
        self.do_test_in_directory(u'Storno in Finesse')

    def test_konten_zuordnungen(self):
        # Testet die Zuordnungen von Konten zwischen Finesse und VF über Einträge in der Config-Datei.
        self.do_test_in_directory(u'Konten-Zuordnungen')

    def test_inkompatible_aenderungen_im_vf(self):
        # Buchungen können nachträglich im VF praktisch beliebig geändert werden, inklusive Änderung der
        # Konten. In solchen Fällen wird die alte Buchung in Finesse storniert und eine neue angelegt.
        self.do_test_in_directory(u'Inkompatible Aenderungen im VF')

    def test_erfolgskonten_nach_vf(self):
        # Später dazu gekommen: wir übernehmen jetzt alle Buchungen auf Erfolgskonten in den VF.
        self.do_test_in_directory(u'Erfolgskonten nach VF')

    def test_importierte_finesse_konten_ohne_config(self):
        # Buchungen, die einmal von Finesse nach VF importiert wurden, müssen unabhängig von der Konfiguration beim
        # nächsten Abgleich wieder gefunden werden.
        self.do_test_in_directory(u'Importierte Finesse Konten ohne Config')

    def test_mehrere_finesse_buchungen_mit_derselben_journalnummer(self):
        # Finesse vergibt in manchen Fällen dieselbe Journalnummer für mehrere Buchungen. Dies wird voll unterstützt,
        # solange die Buchungen sich in ihren Konten unterscheiden.
        self.do_test_in_directory(u'Mehrere Finesse Buchungen mit derselben Journalnummer')

    def test_fehler_mit_mehreren_finesse_buchungen_zur_selben_journalnummer(self):
        # Buchungen mit derselbe Journalnummer müssen sich in den Konten unterscheiden. Dieser Test überprüft die
        # entsprechende Fehlermeldung.
        self.do_test_in_directory(u'Fehler mit mehreren Finesse Buchungen zur selben Journalnummer')

    def test_gutschrift_mitglied_fuer_ausgelegte_rechnung(self):
        # Testet die richtige Wiedererkennung einer solchen Gutschrift aus Finesse im VF.
        self.do_test_in_directory(u'Gutschrift Mitglied für ausgelegte Rechnung')

    def test_kontentausch_mit_steuer(self):
        self.do_test_in_directory(u'Kontentausch mit Steuer')

    def test_null_buchung_im_vf(self):
        # In VF sind Buchungen mit Betrag 0 möglich. Finesse mag das nicht, also müssen solche Buchungen ignoriert
        # werden.
        self.do_test_in_directory(u'Null-Buchung im VF')

    def test_ausgenommene_konten_finesse_nach_vf(self):
        # Einige Konten können für die Übertragung von Finesse ausgenommen werden, selbst wenn das andere Konto
        # eigentlich übertragen werden müsste. Das wird für die jährlichen Saldenvorträge verwendet.
        # Der Test enthält zwei Finesse-Buchungen für dasselbe Mitgliedskonto, von denen nur eine übernommen werden darf.
        self.do_test_in_directory(u'Ausgenommene Konten Finesse nach VF')

    def test_steuerfall_mit_art_keine(self):
        # Dieser Fall hat ursprünglich VF-Imports mit "None" als Steuerkonto erzeugt.
        self.do_test_in_directory(u'Steuerfall mit Art keine')

    def test_ignorieren_von_kostenstellenaenderungen(self):
        # Dieses Feature wurde für den Übergang von 2016 nach 2017 eingebaut.
        self.do_test_in_directory(u'Ignorieren von Kostenstellenaenderungen')

    def test_aenderung_des_steuerfalls_im_vf(self):
        # Zur Sicherheit: ein Test, der Stornieren samt neuer Buchung nach Änderung des Steuerfalls im VF testet.
        self.do_test_in_directory(u'Aenderung des Steuerfalls im VF')

    def test_nicht_zu_uebertragende_buchung_in_finesse(self):
        # Buchungen aus Finesse mit 9 9en in "Beleg 2" werden für den Übertrag zum VF ignoriert.
        self.do_test_in_directory(u'Nicht zu uebertragende Buchung in Finesse')

    def test_buchung_zwischen_erfolgskonten(self):
        # Buchungen zwischen zwei Konten mit Kostenstelle nehmen dieselbe Kostenstelle für beide Seiten.
        self.do_test_in_directory(u'Buchung zwischen Erfolgskonten')

    def test_fehlende_konten(self):
        # Zumindest im VF ist es möglich, Buchungen mit einem fehlenden Konto zu erzeugen. Dies muss eine
        # vernünftige Fehlermeldung erzeugen.
        self.do_test_in_directory(u'Fehlende Konten')

    def test_vf_konto_altes_format_mit_kostennummer(self):
        # Test der Fehlermeldung wenn VF-Kontonummern im alten Format <Konto>-<Kostenstelle> gefunden werden.
        self.do_test_in_directory(u'VF Konto altes Format mit Kostennummer')

    def test_kostenstellen_mapping(self):
        # Test von mappings von Kostenstellen zwischen den beiden Seiten
        self.do_test_in_directory(u'Kostenstellen-Mapping')

    def test_mehrfach_belegte_Steuercodes(self):
        # Überraschenderweise belegt Finesse Steuercodes mehrfach wenn sich der Umsatzsteuersatz ändert.
        self.do_test_in_directory(u'Mehrfach belegte Steuercodes')

    def test_storno_wegen_steuersatzaenderung_mit_gleichem_steuercode(self):
        # Bei Änderung des Steuersatzes im VF muss die Finesse-Buchung storniert und neu angelegt werden.
        self.do_test_in_directory(u'Storno wegen Steuersatzaenderung mit gleichem Steuercode')

    def test_manuelle_korrektur_fuer_mehrfach_belegten_steuercode(self):
        self.do_test_in_directory(u'Manuelle Korrektur fuer mehrfach belegten Steuercode')

    def do_test_in_directory(self, test_dir):
        controller = VereinsFinesse.MainController.MainController()

        # Determine and load configuration file
        config_path = os.path.join(test_dir, u'Config.yaml')
        if not os.path.exists(config_path):
            config_path = u'TestConfig.yaml'

        f = open(config_path, 'rb')
        controller.read_config(f)

        # Import data
        controller.import_vf(os.path.join(test_dir, u'vf_input.csv'))
        controller.import_finesse(os.path.join(test_dir, u'finesse_input.CSV'))

        controller.connectImportedVFBuchungen()
        controller.connectImportedFinesseBuchungen()
        controller.entferne_stornierte_finesse_buchungen()

        # Write results to files.
        vf_result_path = self.write_vf_result(test_dir, controller)
        finesse_result_path = self.write_finesse_result(test_dir, controller)
        fehlerhafte_buchungen_result_path = self.write_fehlerhafte_buchungen(test_dir, controller)

        # Compare results.
        self.check_vf_result(test_dir, vf_result_path)
        self.check_finesse_result(test_dir, finesse_result_path)
        self.check_fehlerhafte_buchungen(test_dir, fehlerhafte_buchungen_result_path )

    def write_vf_result(self, test_dir, controller):
        vf_export_list = controller.finesseBuchungenForExportToVF()
        if len(vf_export_list ) == 0:
            return None
        result_path = os.path.join(test_dir, u'vf_result.csv')
        f = open(result_path , 'w+b')
        controller.exportFinesseBuchungenToVF(vf_export_list , f)
        f.close()
        return result_path

    def check_vf_result(self, test_dir, result_path):
        expected_path = os.path.join(test_dir, u'vf_expected.csv')
        if result_path:
            matches = False
            if os.path.exists(expected_path):
                matches = filecmp.cmp(result_path , expected_path)
            self.assertTrue(matches, "VF results do not match expectation")
            if matches: # else leave it available for inspection
                os.remove(result_path)
        else:
            self.assertFalse(os.path.exists(expected_path), "Expected vf results, but non were produced")

    def write_finesse_result(self, test_dir, controller):
        finesse_export_list = controller.vfBuchungenForExportToFinesse()
        if len(finesse_export_list) == 0:
            return None
        result_path = os.path.join(test_dir, u'finesse_result.csv')
        f = open(result_path, 'w+b')
        controller.exportVFBuchungenToFinesse(finesse_export_list, f)
        f.close()
        return result_path

    def check_finesse_result(self, test_dir, result_path):
        expected_path = os.path.join(test_dir, u'finesse_expected.csv')
        if result_path:
            matches = False
            if os.path.exists(expected_path):
                matches = filecmp.cmp(result_path, expected_path)
            self.assertTrue(matches, "Finesse results do not match expectation")
            if matches:  # else leave it available for inspection
                os.remove(result_path)
        else:
            self.assertFalse(os.path.exists(expected_path), "Expected finesse results, but non were produced")

    def write_fehlerhafte_buchungen(self, test_dir, controller):
        if not controller.has_fehlerhafte_buchungen:
            return None
        result_path = os.path.join(test_dir, u'fehler_result.csv')
        controller.report_fehlerhafte_buchungen(result_path)
        return result_path

    def check_fehlerhafte_buchungen(self, test_dir, result_path):
        expected_path = os.path.join(test_dir, u'fehler_expected.csv')
        if result_path:
            matches = False
            if os.path.exists(expected_path):
                matches = filecmp.cmp(result_path, expected_path)
            self.assertTrue(matches, "Fehlerhafte Buchungen do not match expectation")
            if matches: # else leave it available for inspection
                os.remove(result_path)
        else:
            self.assertFalse(os.path.exists(expected_path), "Expected Fehlerhafte Buchungen, but non were produced")

if __name__ == '__main__':
    unittest.main()
