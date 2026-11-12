"""Isolated SQLite simulations for direct lead ownership and ABC matching."""

import unittest
from datetime import datetime
from io import BytesIO
from uuid import uuid4

from openpyxl import Workbook
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.integrations.excel_import.service import confirm_import, preview_import
from app.models import (
    Customer,
    CustomerAssignmentHistory,
    Department,
    ExcelImportUnmatchedRecord,
    Order,
    User,
)
from app.routers.leads import create_lead
from app.schemas import LeadCreate
from app.utils import customer_scope_condition


def _abc_workbook(external_id: str, name: str, phone: str, order_id: str) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "流水"
    sheet.append([
        "患者档案号", "患者姓名", "手机号", "收费单号", "收费时间", "支付方式",
        "实收", "基金支付总额", "非基金支付总额", "一级分类", "项目名称",
    ])
    sheet.append([
        external_id, name, phone, order_id, datetime(2026, 11, 12, 10, 0),
        "ABC支付(微信)", 258, 0, 258, "治疗", "模拟治疗项目",
    ])
    detail = workbook.create_sheet("明细")
    detail.append([
        "患者档案号", "患者姓名", "手机号", "收费单号", "收费时间", "项目名称",
        "明细金额", "一级分类",
    ])
    detail.append([
        external_id, name, phone, order_id, datetime(2026, 11, 12, 10, 0),
        "模拟治疗项目", 258, "治疗",
    ])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


class LeadAutoAssignmentTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        event.listen(
            self.engine,
            "connect",
            lambda connection, _: connection.create_function(
                "concat", -1, lambda *values: "".join("" if value is None else str(value) for value in values)
            ),
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        department = Department(name=f"模拟部门-{uuid4().hex[:8]}")
        self.db.add(department)
        self.db.flush()
        self.sales01 = User(
            username=f"sales01-{uuid4().hex[:8]}", full_name="模拟业务员甲",
            password_hash="test-only", role="salesperson", department_id=department.id,
            is_active=True,
        )
        self.sales02 = User(
            username=f"sales02-{uuid4().hex[:8]}", full_name="模拟业务员乙",
            password_hash="test-only", role="salesperson", department_id=department.id,
            is_active=True,
        )
        self.admin = User(
            username=f"admin-{uuid4().hex[:8]}", full_name="模拟管理员",
            password_hash="test-only", role="admin", department_id=department.id,
            is_active=True,
        )
        self.db.add_all([self.sales01, self.sales02, self.admin])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _report(self, name: str, phone: str, submission_id: str):
        result = create_lead(
            LeadCreate(name=name, phone=phone, submission_id=submission_id),
            db=self.db,
            user=self.sales01,
        )
        self.db.expire_all()
        customer = self.db.get(Customer, result["lead_id"])
        return result, customer

    def test_report_first_then_abc_import_attaches_to_reporting_salesperson(self):
        suffix = uuid4().hex[:8]
        phone = f"138{int(suffix[:8], 16) % 100_000_000:08d}"
        name = f"模拟客户甲-{suffix}"
        external_id = f"ABC-{suffix}"
        transaction_id = f"TX-{suffix}"

        result, customer = self._report(name, phone, f"submission-{suffix}")
        self.assertEqual(result["status"], "assigned")
        self.assertEqual(customer.lead_status, "assigned")
        self.assertEqual(customer.reported_by_id, self.sales01.id)
        self.assertEqual(customer.assigned_to_id, self.sales01.id)
        self.assertIsNone(customer.reviewed_at)
        history = self.db.scalar(
            select(CustomerAssignmentHistory).where(CustomerAssignmentHistory.customer_id == customer.id)
        )
        self.assertEqual(history.new_salesperson_id, self.sales01.id)
        self.assertEqual(history.changed_by_id, self.sales01.id)

        data = _abc_workbook(external_id, name, phone, transaction_id)
        batch = preview_import(self.db, "mock-abc.xlsx", data, self.admin.id)
        self.assertEqual(batch.matched_customers, 1)
        self.assertEqual(batch.unmatched_customers, 0)
        confirm_import(self.db, batch, self.admin.id)
        self.db.commit()

        order = self.db.scalar(select(Order).where(Order.external_transaction_id == transaction_id))
        self.assertIsNotNone(order)
        self.assertEqual(order.customer_id, customer.id)
        self.assertEqual(customer.external_customer_id, external_id)
        self.assertIn(customer, self.db.scalars(select(Customer).where(customer_scope_condition(self.sales01))).all())
        self.assertNotIn(customer, self.db.scalars(select(Customer).where(customer_scope_condition(self.sales02))).all())

    def test_abc_first_then_report_moves_history_to_reporting_salesperson(self):
        suffix = uuid4().hex[:8]
        phone = f"139{int(suffix[:8], 16) % 100_000_000:08d}"
        name = f"模拟客户乙-{suffix}"
        external_id = f"ABC-{suffix}"
        transaction_id = f"TX-{suffix}"
        data = _abc_workbook(external_id, name, phone, transaction_id)

        batch = preview_import(self.db, "mock-abc-first.xlsx", data, self.admin.id)
        self.assertEqual(batch.unmatched_customers, 1)
        confirm_import(self.db, batch, self.admin.id)
        self.db.commit()
        placeholder = self.db.scalar(select(Customer).where(Customer.external_customer_id == external_id))
        order_before = self.db.scalar(select(Order).where(Order.external_transaction_id == transaction_id))
        self.assertIsNotNone(placeholder)
        self.assertIsNotNone(order_before)
        self.assertIsNone(placeholder.assigned_to_id)

        _, customer = self._report(name, phone, f"submission-{suffix}")
        self.db.expire_all()
        customer = self.db.get(Customer, customer.id)
        moved_order = self.db.scalar(select(Order).where(Order.external_transaction_id == transaction_id))
        unmatched = self.db.scalar(
            select(ExcelImportUnmatchedRecord).where(ExcelImportUnmatchedRecord.external_customer_id == external_id)
        )
        self.assertEqual(customer.assigned_to_id, self.sales01.id)
        self.assertEqual(customer.external_customer_id, external_id)
        self.assertEqual(moved_order.id, order_before.id)
        self.assertEqual(moved_order.customer_id, customer.id)
        self.assertEqual(unmatched.status, "bound")
        self.assertEqual(unmatched.customer_id, customer.id)


if __name__ == "__main__":
    unittest.main()
