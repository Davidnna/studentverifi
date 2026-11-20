"""No database required: university catalogue and name/department aliases."""
import unittest
from academic_catalogue import academic_catalogue_counts, resolve_department, resolve_faculty


class CatalogueTests(unittest.TestCase):
    def test_published_counts(self):
        self.assertEqual(academic_catalogue_counts(), (10, 59))

    def test_department_aliases(self):
        self.assertEqual(resolve_department("English and Literary Studies"),
                         ("Social Sciences and Humanities", "English Language / Literature"))
        self.assertEqual(resolve_department("Electrical Engineering"),
                         ("Engineering", "Electrical & Electronics Engineering"))

    def test_unknown_departments_rejected(self):
        with self.assertRaises(ValueError):
            resolve_department("Invented Department")

    def test_faculty_aliases(self):
        self.assertEqual(resolve_faculty("Faculty of Science"), "Science")


if __name__ == '__main__':
    unittest.main()
