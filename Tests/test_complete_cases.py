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
        # Finesse vergibt in manchen Fällen dieselbe Journalnummer für mehrere Buchungen.
        # Bisher unterstützen wir den Import solcher Buchungen in den Vereinsflieger nicht. Allerdings kann
        # eine Buchung einer solchen Gruppe in VF importiert werden.
        self.do_test_in_directory(u'Mehrere Finesse Buchungen mit derselben Journalnummer')

    def test_gutschrift_mitglied_fuer_ausgelegte_rechnung(self):
        # Testet die richtige Wiedererkennung einer solchen Gutschrift aus Finesse im VF.
        self.do_test_in_directory(u'Gutschrift Mitglied für ausgelegte Rechnung')

    def test_kontentausch_mit_steuer(self):
        self.do_test_in_directory(u'Kontentausch mit Steuer')

    def test_null_buchung_im_vf(self):
        # In VF sind Buchungen mit Betrag 0 möglich. Finesse mag das nicht, also müssen solche Buchungen ignoriert
        # werden.
        self.do_test_in_directory(u'Null-Buchung im VF')

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

        # Export to VF
        self.handle_export_to_vf(test_dir, controller)

        # Export to Finesse
        self.handle_export_to_finesse(test_dir, controller)

        # Fehlerhafte Buchungen
        self.handle_fehlerhafte_buchungen(test_dir, controller)

    def handle_export_to_vf(self, test_dir, controller):
        expected_path = os.path.join(test_dir, u'vf_expected.csv')
        vf_export_list = controller.finesseBuchungenForExportToVF()
        if len(vf_export_list ) > 0:
            result_path = os.path.join(test_dir, u'vf_result.csv')
            f = open(result_path , 'w+b')
            controller.exportFinesseBuchungenToVF(vf_export_list , f)
            f.close()
            matches = False
            if os.path.exists(expected_path):
                matches = filecmp.cmp(result_path , expected_path)
            self.assertTrue(matches, "VF results do not match expectation")
            if matches: # else leave it available for inspection
                os.remove(result_path)
        else:
            self.assertFalse(os.path.exists(expected_path), "Expected vf results, but non were produced")

    def handle_export_to_finesse(self, test_dir, controller):
        expected_path = os.path.join(test_dir, u'finesse_expected.csv')
        finesse_export_list = controller.vfBuchungenForExportToFinesse()
        if len(finesse_export_list) > 0:
            result_path = os.path.join(test_dir, u'finesse_result.csv')
            f = open(result_path, 'w+b')
            controller.exportVFBuchungenToFinesse(finesse_export_list, f)
            f.close()
            matches = False
            if os.path.exists(expected_path):
                matches = filecmp.cmp(result_path, expected_path)
            self.assertTrue(matches, "Finesse results do not match expectation")
            if matches:  # else leave it available for inspection
                os.remove(result_path)
        else:
            self.assertFalse(os.path.exists(expected_path), "Expected finesse results, but non were produced")

    def handle_fehlerhafte_buchungen(self, test_dir, controller):
        expected_path = os.path.join(test_dir, u'fehler_expected.csv')
        if controller.has_fehlerhafte_buchungen:
            result_path = os.path.join(test_dir, u'fehler_result.csv')
            controller.report_fehlerhafte_buchungen(result_path)
            matches = False
            if os.path.exists(expected_path):
                matches = filecmp.cmp(result_path , expected_path)
            self.assertTrue(matches, "Fehlerhafte Buchungen do not match expectation")
            if matches: # else leave it available for inspection
                os.remove(result_path)
        else:
            self.assertFalse(os.path.exists(expected_path), "Expected Fehlerhafte Buchungen, but non were produced")

if __name__ == '__main__':
    unittest.main()
