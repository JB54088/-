"""企业微信适配层预留。

V1 不直接请求企业微信 API；这里集中放 OAuth、UserID 映射和消息能力的接口，
后续接入时无需改动业务路由。
"""


class WecomService:
    def build_oauth_url(self, redirect_uri: str, state: str) -> str:
        raise NotImplementedError("请配置企业微信 CORP_ID、AGENT_ID 后接入 OAuth")

    def exchange_code(self, code: str) -> dict:
        raise NotImplementedError("V1 暂未接入企业微信 OAuth")

    def map_user_id(self, wecom_user_id: str) -> int | None:
        return None


wecom_service = WecomService()
