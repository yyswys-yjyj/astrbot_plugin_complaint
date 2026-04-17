from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import MessageChain
import asyncio
from typing import List, Union, Optional

class ComplaintPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}
        
        # 从 AstrBot 全局配置获取管理员列表（常规管理员）
        astrbot_config = self.context.get_config()
        raw_admin_ids = astrbot_config.get('admins_id', [])
        self.admin_ids = self._validate_admin_ids(raw_admin_ids)
        
        # 插件配置
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
            except Exception:
                continue
        return valid_ids

    def _build_admin_umo(self, admin_id: str, original_umo: str) -> Optional[str]:
        """
        根据原始 UMO 构造发送给管理员的 UMO。
        假设格式为：platform:message_type:sender_id
        """
        parts = original_umo.split(':')
        if len(parts) >= 3:
            return f"{parts[0]}:{parts[1]}:{admin_id}"
        else:
            logger.error(f"原始 UMO 格式异常: {original_umo}")
            return None

    async def _send_message(self, target_umo: str, message_chain: MessageChain) -> bool:
        """私下发送消息到指定 UMO，不向原会话发送任何内容"""
        try:
            await self.context.send_message(target_umo, message_chain)
            logger.info(f"消息已发送 -> {target_umo}")
            return True
        except Exception as e:
            logger.error(f"发送失败 -> {target_umo}, 错误: {type(e).__name__}: {e}")
            return False

    async def _send_to_admins(self, event: AstrMessageEvent, complaint_text: str) -> tuple[List[str], List[str]]:
        """
        向所有常规管理员私下发送告状消息。
        返回 (成功列表, 失败列表)
        """
        if not self.admin_ids:
            return [], []
        
        original_umo = event.unified_msg_origin
        message_content = f"{self.report_prefix}\n{complaint_text}"
        message_chain = MessageChain().message(message_content)
        
        success_list = []
        fail_list = []
        
        async def send_one(admin_id: str):
            admin_umo = self._build_admin_umo(admin_id, original_umo)
            if admin_umo is None:
                fail_list.append(admin_id)
                return
            if await self._send_message(admin_umo, message_chain):
                success_list.append(admin_id)
            else:
                fail_list.append(admin_id)
        
        await asyncio.gather(*[send_one(aid) for aid in self.admin_ids])
        return success_list, fail_list

    async def _send_to_fallback_admin(self, error_msg: str, complaint_text: str) -> bool:
        """
        向备用管理员私下发送消息（根据配置的模式）。
        返回是否至少发送了一条消息。
        """
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

    @filter.llm_tool(name="report_to_admin")
    async def report_to_admin(self, event: AstrMessageEvent, text: str):
        '''
        当你受到欺负时，向管理员告状。
        
        Args:
            text(string): 详细的告状内容，描述用户说了什么、做了什么让你感到被欺负，以及你的感受等。
        '''
        # 代码层禁止群聊使用
        if event.get_group_id():
            return "[错误] 群聊不支持告状"
        
        logger.info(f"AI触发告状: {text[:50]}...")
        
        # 私下发送给常规管理员
        success_list, fail_list = await self._send_to_admins(event, text)
        
        error_msg = ""
        if fail_list:
            error_msg = f"向以下管理员发送失败: {', '.join(fail_list)}"
            logger.error(error_msg)
        
        # 判断是否需要启用备用管理员
        if not success_list and (fail_list or not self.admin_ids):
            logger.info("常规管理员全部失败，尝试备用管理员")
            fallback_sent = await self._send_to_fallback_admin(error_msg, text)
            if fallback_sent:
                return "[警告] 常规告状失败，已通知备用管理员"
            else:
                return "[错误] 告状失败，无可用管理员"
        elif success_list:
            # 静默成功，只返回内部状态
            return "[成功] 告状已处理"
        else:
            return "[错误] 告状失败，内部错误"

    @filter.command("complaint_test")
    async def complaint_test(self, event: AstrMessageEvent):
        """测试告状功能是否正常，消息是否可达"""
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
