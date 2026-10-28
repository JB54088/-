"""Business users can update only their own display name."""

import unittest
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app.models import User
from app.routers.auth import apply_profile_update, update_my_profile
from app.schemas import UserProfileUpdate


class UserProfileUpdateTest(unittest.TestCase):
    class FakeSession:
        def __init__(self):
            self.commits = 0
            self.refreshed = None

        def commit(self):
            self.commits += 1

        def refresh(self, user):
            self.refreshed = user

    def test_profile_endpoint_commits_and_returns_updated_brief(self):
        user = User(
            id=123,
            username="sales01",
            full_name="旧姓名",
            password_hash="unused",
            role="salesperson",
        )
        db = self.FakeSession()
        result = update_my_profile(
            UserProfileUpdate(display_name="新姓名"), db=db, user=user
        )
        self.assertEqual(result.full_name, "新姓名")
        self.assertEqual(result.username, "sales01")
        self.assertEqual(result.role, "salesperson")
        self.assertEqual(db.commits, 1)
        self.assertIs(db.refreshed, user)

    def test_trims_name_and_preserves_login_and_role(self):
        user = User(
            id=123,
            username=f"sales-{uuid4().hex[:8]}",
            full_name="旧姓名",
            password_hash="unused",
            role="salesperson",
        )
        updated = apply_profile_update(user, UserProfileUpdate(display_name="  新姓名  "))
        self.assertEqual(updated.full_name, "新姓名")
        self.assertEqual(updated.username, user.username)
        self.assertEqual(updated.role, "salesperson")

    def test_admin_cannot_use_self_service_name_update(self):
        user = User(
            id=1,
            username="admin01",
            full_name="管理员",
            password_hash="unused",
            role="admin",
        )
        with self.assertRaises(HTTPException) as raised:
            apply_profile_update(user, UserProfileUpdate(display_name="新姓名"))
        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(user.full_name, "管理员")

    def test_blank_name_and_forbidden_fields_are_rejected(self):
        with self.assertRaises(ValidationError):
            UserProfileUpdate(display_name="   ")
        with self.assertRaises(ValidationError):
            UserProfileUpdate(display_name="新姓名", username="admin01")

    def test_name_length_is_limited(self):
        with self.assertRaises(ValidationError):
            UserProfileUpdate(display_name="名" * 81)


if __name__ == "__main__":
    unittest.main()
