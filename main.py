from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import AstrBotConfig
from astrbot.api import logger
from astrbot.api.message_components import Plain

@register("astrbot_plugin_complaint", "yyswys-yjyj", "一个让AI在受欺负时向管理员告状的插件", "1.0.0")
class ReportPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}
        
        # 从AstrBot系统配置中获取管理员列表
        astrbot_config = self.context.get_config()
        self.admin_ids = astrbot_config.get('admins_id', [])
        
        # 从插件配置中获取告状前缀
        self.report_prefix = self.config.get('report_prefix', '【🤖 机器人告状】')
        
        if not self.admin_ids:
            logger.warning("告状插件：系统未配置管理员(admins_id)，告状功能将无法发送消息。")

    async def _send_to_admins_napcat(self, event: AstrMessageEvent, text: str):
        """使用NapCat API向所有系统管理员发送私聊消息（仅支持aiocqhttp平台）"""
        # 检查平台
        if event.get_platform_name() != "aiocqhttp":
            logger.error(f"当前平台 {event.get_platform_name()} 不支持NapCat API调用")
            return False
            
        if not self.admin_ids:
            return False

        # 获取NapCat客户端
        try:
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
            assert isinstance(event, AiocqhttpMessageEvent)
            client = event.bot  # 得到NapCat客户端
        except (ImportError, AssertionError) as e:
            logger.error(f"获取NapCat客户端失败: {e}")
            return False

        # 构建消息内容
        source_info = f"来自用户 {event.get_sender_name()}({event.get_sender_id()})"
        if event.get_group_id():
            source_info += f" 在群 {event.get_group_id()} 中"
        
        # 添加原始消息（如果有）
        if event.message_str:
            source_info += f"\n\n📝 用户说: {event.message_str}"
        
        final_message = f"{self.report_prefix}\n{text}\n\n---\n{source_info}"

        success = False
        for admin_id in self.admin_ids:
            try:
                # 使用NapCat API发送私聊消息
                # 参考NapCat文档：send_private_msg接口
                payload = {
                    "user_id": int(admin_id),  # NapCat API需要整数类型的QQ号
                    "message": final_message,
                    "auto_escape": False  # 是否解析CQ码
                }
                
                # 调用协议端API
                ret = await client.api.call_action('send_private_msg', **payload)
                logger.info(f"向管理员 {admin_id} 发送告状消息成功: {ret}")
                success = True
                
            except Exception as e:
                logger.error(f"向管理员 {admin_id} 发送失败: {e}")
        
        return success

    @filter.llm_tool(name="report_to_admin")
    async def report_to_admin(self, event: AstrMessageEvent, text: str):
        '''当你受到欺负时，向管理员告状
        
        Args:
            text(string): 告状内容
        '''
        logger.info(f"AI触发告状: {text[:50]}...")
        
        if not self.admin_ids:
            logger.error("无管理员配置")
            return "告状失败"
        
        # 使用NapCat API发送
        success = await self._send_to_admins_napcat(event, text)
        
        return "已记录" if success else "告状失败"
