import pymysql
from dbutils.pooled_db import PooledDB
from typing import Optional
from log import logger

"""
  │    方法     │    用途     │                         示例                         │
  ├─────────────┼─────────────┼──────────────────────────────────────────────────────┤
  │ select      │ 查多条      │ db.select('users', where='age > %s', params=(18,))   │
  ├─────────────┼─────────────┼──────────────────────────────────────────────────────┤
  │ select_one  │ 查单条      │ db.select_one('users', where='id = %s', params=(1,)) │
  ├─────────────┼─────────────┼──────────────────────────────────────────────────────┤
  │ insert      │ 插入一条    │ db.insert('users', {'name': '张三', 'age': 18})      │
  ├─────────────┼─────────────┼──────────────────────────────────────────────────────┤
  │ insert_many │ 批量插入    │ db.insert('users', [{'name': 'a'}, {'name': 'b'}])   │
  ├─────────────┼─────────────┼──────────────────────────────────────────────────────┤
  │ update      │ 更新        │ db.update('users', {'age': 20}, 'id = %s', (1,))     │
  ├─────────────┼─────────────┼──────────────────────────────────────────────────────┤
  │ delete      │ 删除        │ db.delete('users', 'id = %s', (1,))                  │
  ├─────────────┼─────────────┼──────────────────────────────────────────────────────┤
  │ execute     │ 执行任意SQL │ db.execute('CREATE TABLE ...')                       │
"""

class Database:
    """
    基于连接池的数据库操作类
    连接池原理：
    - 初始化时创建 mincached 个连接放池里备用
    - 请求来了从池里取，用完还回去（不是关闭）
    - 并发超过 mincached 时，自动新建，最多到 maxconnections
    - 超过 maxconnections 时，根据 blocking 决定排队还是报错
    """

    def __init__(self, host, port, user, password, db, charset='utf8mb4'):
        self.pool = PooledDB(
            creator=pymysql,
            maxconnections=10,
            mincached=2,
            maxcached=5,
            blocking=True,
            maxusage=None,
            ping=1,
            host=host,
            port=port,
            user=user,
            password=password,
            db=db,
            charset=charset,
        )
        self._validate()

    def _get_conn(self) -> pymysql.Connection:
        """从池里取一个连接"""
        return self.pool.connection()

    def _validate(self):
        """
        初始化时验证数据库配置是否正确
        只在启动时跑一次，不影响后续性能
        """
        try:
            conn = self.pool.connection()
            conn.close()
            logger.info("数据库连接验证成功")
        except pymysql.err.ProgrammingError as e:
            logger.error(f"数据库配置错误: {e}")
            raise
        except ValueError as e:
            logger.error(f"参数错误: {e}")
            raise
        except pymysql.err.OperationalError as e:
            logger.error(f"数据库无法连接: {e}")
            raise

    @staticmethod
    def _validate_identifier(name: str) -> None:
        """校验表名/列名是否合法（防SQL注入）"""
        if not name.isidentifier():
            raise ValueError(f"非法标识符: {name}")

    def select(self, table: str, columns: list = None,
               where: str = None, params: tuple = None,
               order_by: str = None, limit: int = None) -> list[dict]:
        """
        查询多条记录
        :param table: 表名
        :param columns: 列名列表，None则查询全部
        :param where: WHERE条件（用%s占位值）
        :param params: WHERE条件的参数元组
        :param order_by: 排序字段，如 "id DESC"
        :param limit: 限制返回条数
        :return: 字典列表
        """
        self._validate_identifier(table)
        if columns:
            for col in columns:
                self._validate_identifier(col)

        cols = ', '.join(columns) if columns else '*'
        sql = f"SELECT {cols} FROM {table}"
        if where:
            sql += f" WHERE {where}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        if limit:
            sql += f" LIMIT {limit}"

        conn = self._get_conn()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(sql, params)
                result = cur.fetchall()
                logger.debug(f"查询成功: {sql}, 返回{len(result)}条")
                return result
        finally:
            conn.close()

    def select_one(self, table: str, columns: list = None,
                   where: str = None, params: tuple = None) -> Optional[dict]:
        """
        查询单条记录
        :return: 字典或None
        """
        self._validate_identifier(table)
        if columns:
            for col in columns:
                self._validate_identifier(col)

        cols = ', '.join(columns) if columns else '*'
        sql = f"SELECT {cols} FROM {table}"
        if where:
            sql += f" WHERE {where}"

        conn = self._get_conn()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(sql, params)
                result = cur.fetchone()
                logger.debug(f"查询成功: {sql}")
                return result
        finally:
            conn.close()

    def insert(self, table: str, data: dict) -> int:
        """
        插入单条记录
        :param table: 表名
        :param data: 字段字典，如 {"name": "张三", "age": 18}
        :return: 影响行数
        """
        self._validate_identifier(table)
        for col in data:
            self._validate_identifier(col)

        columns = ', '.join(data.keys())
        placeholders = ', '.join(['%s'] * len(data))
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"

        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                affected = cur.execute(sql, tuple(data.values()))
                conn.commit()
                logger.debug(f"插入成功: {sql}")
                return affected
        except Exception as e:
            conn.rollback()
            logger.error(f"插入失败: {e}")
            raise
        finally:
            conn.close()

    def insert_many(self, table: str, data_list: list[dict]) -> int:
        """
        批量插入
        :param table: 表名
        :param data_list: 字段字典列表，所有字典的key必须一致
        :return: 影响行数
        """
        if not data_list:
            return 0

        self._validate_identifier(table)
        for col in data_list[0]:
            self._validate_identifier(col)

        columns = ', '.join(data_list[0].keys())
        placeholders = ', '.join(['%s'] * len(data_list[0]))
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        values = [tuple(d.values()) for d in data_list]

        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                affected = cur.executemany(sql, values)
                conn.commit()
                logger.debug(f"批量插入成功: {len(data_list)}条")
                return affected
        except Exception as e:
            conn.rollback()
            logger.error(f"批量插入失败: {e}")
            raise
        finally:
            conn.close()

    def update(self, table: str, data: dict,
               where: str, params: tuple = None) -> int:
        """
        更新记录
        :param table: 表名
        :param data: 要更新的字段字典
        :param where: WHERE条件（用%s占位值）
        :param params: WHERE条件的参数
        :return: 影响行数
        """
        self._validate_identifier(table)
        for col in data:
            self._validate_identifier(col)

        set_clause = ', '.join([f"{k} = %s" for k in data.keys()])
        sql = f"UPDATE {table} SET {set_clause} WHERE {where}"
        # 参数合并：SET的值在前，WHERE的值在后
        all_params = tuple(data.values()) + (params or ())

        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                affected = cur.execute(sql, all_params)
                conn.commit()
                logger.debug(f"更新成功: {sql}, 影响{affected}行")
                return affected
        except Exception as e:
            conn.rollback()
            logger.error(f"更新失败: {e}")
            raise
        finally:
            conn.close()

    def delete(self, table: str, where: str, params: tuple = None) -> int:
        """
        删除记录
        :param table: 表名
        :param where: WHERE条件（用%s占位值）
        :param params: WHERE条件的参数
        :return: 影响行数
        """
        self._validate_identifier(table)
        sql = f"DELETE FROM {table} WHERE {where}"

        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                affected = cur.execute(sql, params)
                conn.commit()
                logger.debug(f"删除成功: {sql}, 影响{affected}行")
                return affected
        except Exception as e:
            conn.rollback()
            logger.error(f"删除失败: {e}")
            raise
        finally:
            conn.close()

    def execute(self, sql: str, params: tuple = None) -> int:
        """
        执行任意SQL（用于建表、复杂查询等）
        :return: 影响行数
        """
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                affected = cur.execute(sql, params)
                conn.commit()
                return affected
        except Exception as e:
            conn.rollback()
            logger.error(f"执行失败: {e}")
            raise
        finally:
            conn.close()
