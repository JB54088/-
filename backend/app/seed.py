import random
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import Customer, CustomerAssignmentHistory, CustomerTag, CustomerTagRelation, Department, ExcelImportBatch, ExcelImportUnmatchedRecord, IntegrationLog, Order, OrderItem, Report, Store, User
from .security import hash_password
from .source_categories import normalize_source_category, normalize_source_level_1


DEMO_USERS = {"admin01", "admin02", "sales01", "sales02", "sales03"}
LEGACY_DEMO_USERS = {"admin", "boss", "leader", "sales", "doctor"}
PASSWORDS = {
    "admin01": "Admin01@123",
    "admin02": "Admin02@123",
    "sales01": "Sales01@123",
    "sales02": "Sales02@123",
    "sales03": "Sales03@123",
}

SYSTEM_DEPARTMENTS = [
    ("客户增长组", "客户线索与增长团队"),
    ("私域运营组", "私域客户经营团队"),
    ("高客经营组", "高价值客户经营团队"),
    ("渠道拓展组", "渠道拓展团队"),
    ("客户成功组", "客户服务与成功团队"),
]
SYSTEM_TAGS = [("高意向", "rose"), ("普通客户", "blue"), ("VIP", "amber"), ("老客户", "violet"), ("高消费", "emerald"), ("待跟进", "orange"), ("已成交", "green"), ("沉睡客户", "gray")]


def ensure_system_data(db: Session) -> None:
    """Ensure accounts/config exist without creating any customer business data."""
    departments = {department.name: department for department in db.scalars(select(Department)).all()}
    for name, description in SYSTEM_DEPARTMENTS:
        if name not in departments:
            department = Department(name=name, description=description)
            db.add(department)
            departments[name] = department
    db.flush()

    account_departments = {"sales01": "客户增长组", "sales02": "私域运营组", "sales03": "高客经营组"}
    account_names = {"admin01": "林总", "admin02": "陈主管", "sales01": "王明", "sales02": "苏晴", "sales03": "叶宁"}
    account_roles = {"admin01": "admin", "admin02": "admin", "sales01": "salesperson", "sales02": "salesperson", "sales03": "salesperson"}
    existing_users = {user.username: user for user in db.scalars(select(User)).all()}
    for username, full_name in account_names.items():
        if username in existing_users:
            continue
        db.add(User(
            username=username,
            full_name=full_name,
            password_hash=hash_password(PASSWORDS[username]),
            role=account_roles[username],
            department=departments.get(account_departments.get(username)),
        ))

    existing_tags = {tag.name for tag in db.scalars(select(CustomerTag)).all()}
    for name, color in SYSTEM_TAGS:
        if name not in existing_tags:
            db.add(CustomerTag(name=name, color=color))
    db.commit()


def _clear_legacy_demo(db: Session) -> None:
    """Replace the original V1 seed once. This is only triggered by the known demo accounts."""
    usernames = set(db.scalars(select(User.username)).all())
    if not usernames.intersection(LEGACY_DEMO_USERS) or usernames.intersection(DEMO_USERS):
        return
    db.execute(delete(OrderItem))
    db.execute(delete(Order))
    db.execute(delete(ExcelImportUnmatchedRecord))
    db.execute(delete(ExcelImportBatch))
    db.execute(delete(CustomerTagRelation))
    db.execute(delete(CustomerAssignmentHistory))
    db.execute(delete(Report))
    db.execute(delete(IntegrationLog))
    db.execute(delete(Customer))
    db.execute(delete(CustomerTag))
    db.execute(delete(Store))
    db.execute(delete(User))
    db.execute(delete(Department))
    db.commit()


def seed_demo_data(db: Session) -> None:
    _clear_legacy_demo(db)
    if db.scalar(select(User.id).where(User.username == "admin01")):
        return
    if db.scalar(select(User.id).limit(1)):
        return

    random.seed(20260826)
    now = datetime.now().replace(microsecond=0)
    department_names = ["客户增长组", "私域运营组", "高客经营组", "渠道拓展组", "客户成功组"]
    departments = [Department(name=name, description=f"{name}客户经营团队") for name in department_names]
    db.add_all(departments)
    db.flush()

    stores = [Store(name=name, address=address) for name, address in [("福州店", "鼓楼区湖东路"), ("厦门店", "思明区环岛路"), ("泉州店", "丰泽区东海大街")]]
    db.add_all(stores)
    db.flush()

    admin01 = User(username="admin01", full_name="林总", password_hash=hash_password(PASSWORDS["admin01"]), role="admin")
    admin02 = User(username="admin02", full_name="陈主管", password_hash=hash_password(PASSWORDS["admin02"]), role="admin")
    sales_users = [
        User(username="sales01", full_name="王明", password_hash=hash_password(PASSWORDS["sales01"]), role="salesperson", department=departments[0]),
        User(username="sales02", full_name="苏晴", password_hash=hash_password(PASSWORDS["sales02"]), role="salesperson", department=departments[1]),
        User(username="sales03", full_name="叶宁", password_hash=hash_password(PASSWORDS["sales03"]), role="salesperson", department=departments[2]),
    ]
    db.add_all([admin01, admin02, *sales_users])
    db.flush()

    tags = [CustomerTag(name=name, color=color) for name, color in [("高意向", "rose"), ("普通客户", "blue"), ("VIP", "amber"), ("老客户", "violet"), ("高消费", "emerald"), ("待跟进", "orange"), ("已成交", "green"), ("沉睡客户", "gray")]]
    db.add_all(tags)
    db.flush()
    tag_by_name = {tag.name: tag for tag in tags}

    sources = ["企业微信", "小红书", "老客转介绍", "抖音", "自然到店", "公众号"]
    customers: list[Customer] = []
    surnames = ["张", "李", "王", "陈", "林", "黄", "赵", "周"]
    given_names = ["安", "悦", "宁", "欣", "然", "琪", "晨", "妍"]
    for index in range(180):
        reporter = sales_users[index % 3]
        assigned = sales_users[index % 3] if index < 150 else None
        created_at = now - timedelta(days=random.randint(0, 180), hours=random.randint(0, 12))
        if assigned:
            lead_status = "converted" if index % 3 == 0 else "assigned"
        else:
            lead_status = "pending" if index < 165 else "unassigned"
        source_value = random.choice(sources)
        source_level_1 = normalize_source_level_1(source_value)
        source_level_2 = {
            "企业微信": "wechat",
            "小红书": "xiaohongshu",
            "老客转介绍": "patient_referral",
            "抖音": "douyin",
            "自然到店": "store_visit",
            "公众号": "online_other",
        }.get(source_value, "unknown")
        customer = Customer(
            external_customer_id=f"DEMO{10001 + index}",
            pool_match_status="matched",
            name=f"{random.choice(surnames)}{random.choice(given_names)}{random.choice(['', '女士', '先生'])}",
            phone=f"1{random.choice([3, 5, 7, 8, 9])}{random.randint(10000000, 99999999)}",
            wechat_id=f"wx_{index + 1001}" if random.random() > 0.35 else None,
            gender=random.choice(["女", "女", "男"]),
            age=random.randint(22, 58),
            source=source_value,
            source_category=normalize_source_category(source_value),
            source_level_1=source_level_1,
            source_level_2=source_level_2,
            notes=random.choice(["首次沟通反馈良好", "关注价格方案", "需要持续跟进", None]),
            department=assigned.department if assigned else None,
            reported_by_id=reporter.id,
            assigned_to_id=assigned.id if assigned else None,
            reported_at=created_at,
            lead_status=lead_status,
            reviewed_by_id=admin01.id if lead_status != "pending" else None,
            reviewed_at=created_at + timedelta(hours=2) if lead_status != "pending" else None,
            member_level=random.choice(["普通", "银卡", "金卡", "VIP"]),
            wechat_status="connected" if random.random() > 0.35 else "unbound",
            status="active",
            first_visit_at=created_at + timedelta(days=random.randint(0, 8)) if lead_status == "converted" else None,
            created_at=created_at,
        )
        customers.append(customer)
    db.add_all(customers)
    db.flush()

    for customer in customers:
        assigned_tags = random.sample(tags, random.randint(1, 3))
        if customer.lead_status == "pending" and tag_by_name["待跟进"] not in assigned_tags:
            assigned_tags[0] = tag_by_name["待跟进"]
        if customer.lead_status == "converted" and tag_by_name["已成交"] not in assigned_tags:
            assigned_tags[0] = tag_by_name["已成交"]
        db.add_all([CustomerTagRelation(customer_id=customer.id, tag_id=tag.id) for tag in {tag.id: tag for tag in assigned_tags}.values()])

    item_catalog = [("客户方案咨询", "问诊", (199, 899)), ("深层清洁", "理疗", (299, 1299)), ("体质评估", "问诊", (99, 399)), ("营养方案", "保健品", (399, 1999)), ("客户管理疗程", "理疗", (599, 2599)), ("精品产品", "其他", (129, 699))]
    payment_methods = ["微信支付", "支付宝", "银行卡", "现金"]
    assigned_customers = [customer for customer in customers if customer.assigned_to_id]
    for index in range(1000):
        customer = random.choice(assigned_customers)
        item_name, category, amount_range = random.choice(item_catalog)
        paid_at = now - timedelta(days=random.randint(0, 180), hours=random.randint(0, 23), minutes=random.randint(0, 59))
        amount = Decimal(str(random.randint(*amount_range)))
        insurance_amount = amount if index % 4 == 0 else Decimal("0")
        self_pay_amount = amount - insurance_amount
        order = Order(
            order_no=f"ORD{paid_at.strftime('%Y%m%d')}{index + 1:04d}",
            external_order_id=f"DEMO-ORD-{index + 1:06d}",
            customer=customer,
            paid_at=paid_at,
            item_name=item_name,
            category=category,
            amount=amount,
            total_amount=amount,
            insurance_amount=insurance_amount,
            self_pay_amount=self_pay_amount,
            payment_type="insurance" if insurance_amount else "self_pay",
            payment_split_status="verified",
            store=random.choice(stores),
            department_id=customer.department_id,
            owner_id=customer.assigned_to_id,
            staff_name="客户服务团队",
            payment_method=random.choice(payment_methods),
            raw_json={"source": "demo", "seed_index": index},
        )
        order.items.append(OrderItem(item_name=item_name, quantity=1, unit_price=amount, amount=amount))
        customer.last_visit_at = max(customer.last_visit_at or paid_at, paid_at)
        if customer.lead_status == "assigned":
            customer.lead_status = "converted"
        db.add(order)

    for index, customer in enumerate(customers[:45]):
        if not customer.assigned_to_id:
            continue
        previous = sales_users[(sales_users.index(customer.assigned_to_user) + 1) % 3]
        db.add(CustomerAssignmentHistory(customer_id=customer.id, previous_salesperson_id=previous.id, new_salesperson_id=customer.assigned_to_id, changed_by_id=admin02.id, change_reason="客户池优化分配", changed_at=now - timedelta(days=index + 1)))
    db.commit()
