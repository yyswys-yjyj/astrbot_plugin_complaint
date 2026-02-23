from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import AstrBotConfig, logger
from astrbot.api.message_components import Plain
from astrbot.api.event import MessageChain
import asyncio
from typing import List, Union

class ComplaintPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}
        
        # 从AstrBot系统配置中获取管理员列表
        astrbot_config = self.context.get_config()
        raw_admin_ids = astrbot_config.get('admins_id', [])
        
        # 预处理并验证管理员ID
        self.admin_ids = self._validate_admin_ids(raw_admin_ids)
        
        # 从插件配置中获取告状前缀
        self.report_prefix = self.config.get('report_prefix', '【🤖 机器人告状】')
        
        if not self.admin_ids:
            logger.warning("告状插件：没有有效管理员ID，告状功能将无法发送消息。")

    def _validate_admin_ids(self, raw_ids: List[Union[str, int]]) -> List[str]:
        """验证并格式化管理员ID"""
        valid_ids = []
        for admin_id in raw_ids:
            try:
                str_id = str(admin_id).strip()
                if str_id:
                    valid_ids.append(str_id)
                else:
                    logger.warning(f"管理员ID为空字符串，已忽略")
            except Exception as e:
                logger.warning(f"管理员ID {admin_id} 格式无效，已忽略: {e}")
        return valid_ids

    async def _send_to_admins(self, event: AstrMessageEvent, text: str) -> bool:
        """使用AstrBot统一消息接口向所有管理员发送私聊消息"""
        if not self.admin_ids:
            logger.error("没有有效管理员ID可发送")
            return False

        # 构建消息内容
        source_info = f"来自用户 {event.get_sender_name()}({event.get_sender_id()})"
        if event.get_group_id():
            source_info += f" 在群 {event.get_group_id()} 中"
        
        if event.message_str and event.message_str != text:
            source_info += f"\n\n📝 用户说: {event.message_str}"
        
        final_message = f"{self.report_prefix}\n{text}\n\n---\n{source_info}"

        # 正确创建消息链 - 使用 MessageChain 而不是列表
        message_chain = MessageChain().message(final_message)

        # 解析当前事件的格式
        current_origin = event.unified_msg_origin
        parts = current_origin.split(':')
        
        if len(parts) >= 3:
            platform = parts[0]      # default
            message_type = parts[1]   # FriendMessage
            # session_id = parts[2]   # 当前用户的ID
        else:
            platform = "default"
            message_type = "FriendMessage"
            logger.warning(f"无法完整解析 unified_msg_origin: {current_origin}")

        # 并发发送任务
        async def send_to_single_admin(admin_id: str):
            try:
                # 构造目标地址 - 使用从当前事件解析出的格式
                target_origin = f"{platform}:{message_type}:{admin_id}"
                
                logger.info(f"尝试向管理员 {admin_id} 发送消息，目标: {target_origin}")
                
                # 使用AstrBot的统一发送接口
                await self.context.send_message(target_origin, message_chain)
                logger.info(f"✅ 已向管理员 {admin_id} 发送告状消息")
                return True
                
            except Exception as e:
                logger.error(f"向管理员 {admin_id} 发送失败: {type(e).__name__}: {e}")
                return False

        # 并发执行所有发送任务
        results = await asyncio.gather(
            *[send_to_single_admin(admin_id) for admin_id in self.admin_ids],
            return_exceptions=False
        )
        
        # 返回是否至少有一个发送成功
        return any(results)

    @filter.llm_tool(name="report_to_admin")
    async def report_to_admin(self, event: AstrMessageEvent, text: str):
        '''
        当你受到欺负时，向管理员告状。
        
        Args:
            text(string): 详细的告状内容，描述用户说了什么、做了什么让你感到被欺负，以及你的感受等。
        '''
        logger.info(f"AI触发告状: {text[:50]}...")
        
        if not self.admin_ids:
            logger.error("无有效管理员，告状失败")
            return "告状失败：无法联系管理员"
        
        success = await self._send_to_admins(event, text)
        return "已记录" if success else "告状失败"
