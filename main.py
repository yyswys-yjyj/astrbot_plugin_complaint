from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import MessageChain
import asyncio
from typing import List, Union, Optional, Tuple

class ComplaintPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}
        
        astrbot_config = self.context.get_config()
        raw_admin_ids = astrbot_config.get('admins_id', [])
        self.admin_ids = self._validate_admin_ids(raw_admin_ids)
        
        self.report_prefix = self.config.get('report_prefix', '【机器人告状】')
        self.fallback_admin_umo = self.config.get('fallback_admin_umo', '').strip()
        self.fallback_send_mode = self.config.get('fallback_send_mode', 'only_error')
        
        if not self.admin_ids and not self.fallback_admin_umo:
            logger.warning("告状插件：未配置任何管理员（常规或备用），告状功能将无法发送消息。")

    def _validate_admin_ids(self, raw_ids: List[Union[str, int]]) -> List[str]:
        """验证并格式化管理员ID"""
        valid_ids = []
        for admin_id in raw_ids:
            try:
                str_id = str(admin_id).strip()
                if str_id:
                    valid_ids.append(str_id)
            except (TypeError, ValueError):
                continue
        return valid_ids

    def _build_admin_umo(self, admin_id: str, original_umo: str) -> Optional[str]:
        """
        根据原始 UMO 构造发送给管理员的 UMO。
        保留原始 UMO 的所有段，仅替换第三段（session_id）为 admin_id。
        假设格式为：platform:message_type:session_id[:extra...]
        """
        parts = original_umo.split(':')
        if len(parts) >= 3:
            new_parts = [parts[0], parts[1], admin_id] + parts[3:]
            return ":".join(new_parts)
        else:
            logger.error(f"原始 UMO 格式异常，无法构造管理员 UMO: {original_umo}")
            return None

    async def _send_message(self, target_umo: str, message_chain: MessageChain) -> bool:
        try:
            await self.context.send_message(target_umo, message_chain)
            logger.info(f"消息已发送 -> {target_umo}")
            return True
        except Exception as e:
            logger.error(f"发送失败 -> {target_umo}, 错误: {type(e).__name__}: {e}")
            return False

    async def _send_to_admins(self, event: AstrMessageEvent, complaint_text: str) -> Tuple[List[str], List[str]]:
        """
        向所有常规管理员私下发送告状消息。
        返回 (成功列表, 失败列表)
        """
        if not self.admin_ids:
            return [], []
        
        original_umo = event.unified_msg_origin
        message_content = f"{self.report_prefix}\n{complaint_text}"
        message_chain = MessageChain().message(message_content)
        
        async def send_one(admin_id: str) -> Tuple[str, bool]:
            admin_umo = self._build_admin_umo(admin_id, original_umo)
            if admin_umo is None:
                return admin_id, False
            success = await self._send_message(admin_umo, message_chain)
            return admin_id, success
        
        results = await asyncio.gather(*[send_one(aid) for aid in self.admin_ids])
        
        success_list = [aid for aid, success in results if success]
        fail_list = [aid for aid, success in results if not success]
        return success_list, fail_list

    async def _send_to_fallback_admin(self, error_msg: str, complaint_text: str) -> bool:
        if not self.fallback_admin_umo:
            return False
        
        mode = self.fallback_send_mode
        
        if mode == 'only_error':
            chain = MessageChain().message(f"【告状失败】\n{error_msg}")
            return await self._send_message(self.fallback_admin_umo, chain)
        elif mode == 'only_complaint':
            chain = MessageChain().message(f"{self.report_prefix}\n{complaint_text}")
            return await self._send_message(self.fallback_admin_umo, chain)
        elif mode == 'both':
            chain_err = MessageChain().message(f"【告状失败】\n{error_msg}")
            chain_complaint = MessageChain().message(f"{self.report_prefix}\n{complaint_text}")
            success_err = await self._send_message(self.fallback_admin_umo, chain_err)
            success_complaint = await self._send_message(self.fallback_admin_umo, chain_complaint)
            return success_err or success_complaint
        else:
            logger.warning(f"未知的备用发送模式: {mode}")
            return False

    def _get_error_msg_for_fallback(self, fail_list: List[str]) -> str:
        """根据失败列表生成备用管理员用的错误信息"""
        if not self.admin_ids:
            return "未配置任何常规管理员"
        elif fail_list:
            return f"向以下管理员发送失败: {', '.join(fail_list)}"
        else:
            return ""

    async def _handle_complaint_result(
        self, success_list: List[str], fail_list: List[str], complaint_text: str
    ) -> str:
        """
        处理发送结果，决定是否使用备用管理员，返回给 LLM 的字符串。
        """
        error_msg = self._get_error_msg_for_fallback(fail_list)
        if error_msg:
            logger.error(error_msg)
        
        # 情况1：至少有一个常规管理员成功
        if success_list:
            return "[成功] 告状已处理"
        
        # 情况2：没有任何常规管理员成功（没有配置或全部失败）
        logger.info("常规管理员全部失败，尝试备用管理员")
        fallback_sent = await self._send_to_fallback_admin(error_msg, complaint_text)
        if fallback_sent:
            return "[警告] 常规告状失败，已通知备用管理员"
        else:
            return "[错误] 告状失败，无可用管理员"

    @filter.llm_tool(name="report_to_admin")
    async def report_to_admin(self, event: AstrMessageEvent, text: str):
        '''
        当你受到欺负时，向管理员告状。
        
        Args:
            text(string): 详细的告状内容，描述用户说了什么、做了什么让你感到被欺负，以及你的感受等。
        '''
        # 群聊中禁止使用，并记录日志
        if event.get_group_id():
            logger.error("机器人在群聊中使用告状工具，已阻止")
            return "[错误] 群聊不支持告状"
        
        logger.info(f"AI触发告状: {text[:50]}...")
        
        success_list, fail_list = await self._send_to_admins(event, text)
        return await self._handle_complaint_result(success_list, fail_list, text)

    @filter.command("complaint_test")
    async def complaint_test(self, event: AstrMessageEvent):
        if event.get_group_id():
            yield event.plain_result("[禁止] 测试指令仅支持私聊")
            return
        
        if not self.admin_ids and not self.fallback_admin_umo:
            yield event.plain_result("[信息] 未配置任何管理员")
            return
        
        test_text = "这是一条来自 complaint_test 指令的测试消息。"
        success_list, fail_list = await self._send_to_admins(event, test_text)
        
        result_parts = []
        if success_list:
            result_parts.append(f"[成功] 发送给: {', '.join(success_list)}")
        if fail_list:
            result_parts.append(f"[失败] 发送失败: {', '.join(fail_list)}")
        
        if self.fallback_admin_umo:
            test_error = "测试错误信息"
            sent = await self._send_to_fallback_admin(test_error, test_text)
            result_parts.append(f"[备用] 备用管理员: {'[成功]' if sent else '[失败]'}")
        
        if not result_parts:
            result_parts.append("[信息] 未执行任何发送")
        
        yield event.plain_result("\n".join(result_parts))
