import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, SmallInteger, Index, Float
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class SiteMessageORM(Base):
    __tablename__ = "site_message"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="主键ID")
    sender = Column(String(100), nullable=False, comment="发送者ID")
    receiver = Column(String(100), nullable=False, comment="接收者ID")
    content = Column(Text, nullable=False, comment="消息内容")
    is_read = Column(SmallInteger, default=0, comment="已读状态：0-未读，1-已读")
    created_at = Column(DateTime, default=datetime.datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now, comment="更新时间")
    read_at = Column(DateTime, nullable=True, comment="阅读时间")

    __table_args__ = (
        Index("idx_receiver_is_read_created_at", "receiver", "is_read", "created_at"),
    )


class UploadedFileORM(Base):
    __tablename__ = "uploaded_file"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="主键ID")
    filename = Column(String(255), nullable=False, unique=True, comment="文件名称")
    file_path = Column(String(500), nullable=False, comment="文件物理路径")
    file_size_mb = Column(Float, nullable=False, comment="文件大小(MB)")
    created_at = Column(DateTime, default=datetime.datetime.now, comment="创建时间")


class AuditLogORM(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="主键ID")
    operator = Column(String(100), nullable=True, index=True, comment="操作人/账号")
    action = Column(String(100), nullable=False, index=True, comment="操作动作")
    resource_type = Column(String(100), nullable=True, comment="操作资源类型")
    resource_id = Column(String(100), nullable=True, comment="操作资源ID")
    ip_address = Column(String(50), nullable=True, comment="操作者IP")
    user_agent = Column(String(500), nullable=True, comment="浏览器User-Agent")
    status = Column(String(20), nullable=False, index=True, comment="执行状态：success/failed")
    details = Column(Text, nullable=True, comment="详细内容(JSON字符串或错误堆栈)")
    request_params = Column(Text, nullable=True, comment="请求参数/传参")
    execution_time = Column(Float, nullable=True, comment="执行耗时(毫秒)")
    method = Column(String(20), nullable=True, comment="请求方式：GET/POST等")
    created_at = Column(DateTime, default=datetime.datetime.now, index=True, comment="记录创建时间")


class PlayerProfileORM(Base):
    __tablename__ = "player_profile"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    player_id = Column(String(100), nullable=False, unique=True, index=True, comment="玩家ID")
    nickname = Column(String(100), nullable=False, comment="昵称")
    beans = Column(Integer, default=10000, nullable=False, comment="欢乐豆")
    total_games = Column(Integer, default=0, nullable=False, comment="总对局数")
    wins = Column(Integer, default=0, nullable=False, comment="胜场数")
    rank_id = Column(Integer, default=1, nullable=False, comment="大级别(1-36)")
    sub_rank = Column(Integer, default=4, nullable=False, comment="子级别(1-4，对应I-IV)")
    stars = Column(Integer, default=0, nullable=False, comment="当前小段位星星数")
    created_at = Column(DateTime, default=datetime.datetime.now, comment="创建时间")


class UserORM(Base):
    __tablename__ = "user_account"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="主键ID")
    username = Column(String(100), nullable=False, unique=True, index=True, comment="账号")
    password = Column(String(255), nullable=False, comment="密码")
    player_id = Column(String(100), nullable=False, unique=True, index=True, comment="关联的Player ID")
    created_at = Column(DateTime, default=datetime.datetime.now, comment="创建时间")



class GameRecordORM(Base):
    __tablename__ = "game_record"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    room_id = Column(String(100), nullable=False, index=True, comment="房间ID")
    player_id = Column(String(100), nullable=False, index=True, comment="玩家ID")
    role = Column(String(20), nullable=False, comment="角色: landlord/farmer")
    result = Column(String(20), nullable=False, comment="结果: win/lose")
    score_change = Column(Integer, nullable=False, comment="欢乐豆变化")
    multiplier = Column(Integer, default=1, comment="倍数")
    created_at = Column(DateTime, default=datetime.datetime.now, index=True, comment="对局时间")




