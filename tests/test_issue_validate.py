import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from issue_validate import validate_member_rows


def member_fields(index, student_no=None, name=None, github=None):
    return {
        f"Member {index} · Student No": student_no or "",
        f"Member {index} · Full Name": name or "",
        f"Member {index} · GitHub Username": github or "",
    }


def complete_member(index):
    return member_fields(
        index,
        student_no=f"EC/2022/{index:03d}",
        name=f"Student {index}",
        github=f"student-{index}",
    )


class ValidateMemberRowsTests(unittest.TestCase):
    def test_two_member_team_requires_members_one_and_two(self):
        form = member_fields(1, "EC/2022/001", "Student 1", "student-1")
        form.update(complete_member(2))
        self.assertEqual(validate_member_rows(form, 2), [])

    def test_three_member_team_requires_members_one_through_three(self):
        form = {}
        for index in range(1, 4):
            form.update(complete_member(index))
        self.assertEqual(validate_member_rows(form, 3), [])

    def test_four_member_team_requires_all_four_members(self):
        form = {}
        for index in range(1, 5):
            form.update(complete_member(index))
        self.assertEqual(validate_member_rows(form, 4), [])

    def test_missing_middle_member_is_rejected_even_if_later_row_is_filled(self):
        form = complete_member(1)
        form.update(complete_member(3))
        errors = validate_member_rows(form, 3)
        self.assertIn("Member 2: Student No is required.", errors)
        self.assertIn("Member 2: Full Name is required.", errors)
        self.assertIn("Member 2: GitHub Username is required.", errors)

    def test_member_one_is_required(self):
        form = complete_member(2)
        errors = validate_member_rows(form, 2)
        self.assertIn("Member 1: Student No is required.", errors)
        self.assertIn("Member 1: Full Name is required.", errors)
        self.assertIn("Member 1: GitHub Username is required.", errors)

    def test_partial_required_row_is_rejected(self):
        form = complete_member(1)
        form.update(member_fields(2, student_no="EC/2022/002"))
        errors = validate_member_rows(form, 2)
        self.assertIn("Member 2: Full Name is required.", errors)
        self.assertIn("Member 2: GitHub Username is required.", errors)

    def test_populated_row_beyond_selected_team_size_is_rejected(self):
        form = complete_member(1)
        form.update(complete_member(2))
        form.update(complete_member(3))
        errors = validate_member_rows(form, 2)
        self.assertTrue(any("Member 3: leave this row blank" in error for error in errors))

    def test_invalid_team_size_still_requires_member_one(self):
        errors = validate_member_rows({}, None)
        self.assertIn("Member 1: Student No is required.", errors)
        self.assertIn("Member 1: Full Name is required.", errors)
        self.assertIn("Member 1: GitHub Username is required.", errors)


if __name__ == "__main__":
    unittest.main()
