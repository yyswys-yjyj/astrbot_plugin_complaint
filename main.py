from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import AstrBotConfig, logger
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
        self.admin_ids = self._validate_admin_ids(raw_admin_ids)
        
        # 加载插件配置
        self.report_prefix = self.config.get('report_prefix', '【🤖 机器人告状】')
        self.message_type_mode = self.config.get('message_type_mode', 'auto')
        self.custom_message_type = self.config.get('custom_message_type', 'FriendMessage')
        
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

    def _get_message_type(self, event: AstrMessageEvent) -> str:
        """
        根据配置获取消息类型
        """
        if self.message_type_mode == "custom":
            logger.debug(f"使用自定义消息类型: {self.custom_message_type}")
            return self.custom_message_type
        
        # auto模式：从事件中提取消息类型
        current_origin = event.unified_msg_origin
        parts = current_origin.split(':')
        
        if len(parts) >= 2:
            source_msg_type = parts[1]
            
            # 智能判断：如果来源是群聊，自动转换为对应的私聊类型
            if "Group" in source_msg_type or "group" in source_msg_type:
                # 群聊转私聊的映射表
                type_mapping = {
                    "GroupMessage": "FriendMessage",
                    "group_message": "private_message",
                    "GroupMsg": "FriendMsg",
                    "group_msg": "private_msg"
                }
                
                # 查找映射，如果找不到则尝试替换
                for group_type, friend_type in type_mapping.items():
                    if source_msg_type == group_type:
                        logger.info(f"auto模式转换消息类型: {source_msg_type} -> {friend_type}")
                        return friend_type
                
                # 通用替换规则
                converted = source_msg_type.replace("Group", "Friend").replace("group", "private")
                logger.info(f"auto模式转换消息类型: {source_msg_type} -> {converted}")
                return converted
            
            return source_msg_type
        
        return "FriendMessage"  # 默认

    async def _send_to_admins(self, event: AstrMessageEvent, text: str) -> bool:
        """向所有管理员发送私聊消息"""
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
        message_chain = MessageChain().message(final_message)

        # 获取消息类型
        message_type = self._get_message_type(event)
        
        # 从 unified_msg_origin 中提取机器人名称（第一部分）
        current_origin = event.unified_msg_origin
        parts = current_origin.split(':')
        bot_name = parts[0] if len(parts) >= 1 else "default"

        # 并发发送任务
        async def send_to_single_admin(admin_id: str):
            try:
                # 使用机器人名称和消息类型构造目标地址
                target_origin = f"{bot_name}:{message_type}:{admin_id}"
                
                logger.info(f"尝试向管理员 {admin_id} 发送消息，目标: {target_origin}")
                await self.context.send_message(target_origin, message_chain)
                logger.info(f"✅ 已向管理员 {admin_id} 发送告状消息")
                return True
                
            except Exception as e:
                logger.error(f"向管理员 {admin_id} 发送失败: {type(e).__name__}: {e}")
                return False

        results = await asyncio.gather(
            *[send_to_single_admin(admin_id) for admin_id in self.admin_ids],
            return_exceptions=False
        )
        
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
