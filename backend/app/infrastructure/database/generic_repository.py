import logging
from typing import Generic, TypeVar, Type, List, Optional
from sqlalchemy.orm import Session

T_Domain = TypeVar('T_Domain')
T_ORM = TypeVar('T_ORM')

logger = logging.getLogger("hmp_ws_service")
class GenericSQLRepository(Generic[T_Domain, T_ORM]):

    """SQLAlchemy 泛型仓储基类，封装基础的 CRUD 操作，不进行 commit"""

    def __init__(self, db: Session, orm_model: Type[T_ORM], domain_model: Type[T_Domain]):
        self.db = db
        self.orm_model = orm_model
        self.domain_model = domain_model

    def _to_domain(self, orm: T_ORM) -> Optional[T_Domain]:
        """将 ORM 对象转换为领域对象，默认使用反射，可由子类重写"""
        if not orm:
            return None
        # 通过反射获取表中的列名，并映射到领域实体
        columns = [c.name for c in self.orm_model.__table__.columns]
        fields = {}
        for col in columns:
            if hasattr(orm, col):
                fields[col] = getattr(orm, col)
        try:
            return self.domain_model(**fields)
        except TypeError as e:
            logger.error(f"Error mapping ORM fields to Domain entity: {e}")
            raise

    def find_by_id(self, entity_id: int) -> Optional[T_Domain]:
        orm = self.db.query(self.orm_model).filter(self.orm_model.id == entity_id).first()
        return self._to_domain(orm) if orm else None

    def find_all(self) -> List[T_Domain]:
        orm_list = self.db.query(self.orm_model).all()
        return [self._to_domain(orm) for orm in orm_list]

    def delete_by_id(self, entity_id: int) -> Optional[T_Domain]:
        orm = self.db.query(self.orm_model).filter(self.orm_model.id == entity_id).first()
        if not orm:
            return None
        domain = self._to_domain(orm)
        self.db.delete(orm)
        return domain
