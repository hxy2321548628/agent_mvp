<!-- .claude/python-style.md -->
# Python 代码规范详细版

### 命名约定

#### 包命名（单数名词）
```python
# ✅ 正确
app/model/user.py
app/model/product.py

# ❌ 错误
app/models/users.py
app/models/products.py
```

#### 文件命名
- 模型文件：单数名词（`user.py`）
- 测试文件：`{module}_test.py`
- 服务文件：小写下划线（`user_service.py`）

#### 变量和函数命名
```python
# ✅ 正确：snake_case
user_name = "John"
def get_user_by_id(user_id: int):
    pass

# ❌ 错误：camelCase
userName = "John"
def getUserById(userId: int):
    pass
```

#### 类命名
```python
# ✅ 正确：PascalCase
class UserService:
    pass

class UserCreate(BaseModel):
    pass
```

### 类型注解（禁止 Any）

```python
# ✅ 正确：明确类型
from typing import List, Optional
from pydantic import BaseModel

def get_users(limit: int) -> List[User]:
    pass

def find_user(email: str) -> Optional[User]:
    pass

# ❌ 错误：使用 Any
from typing import Any

def process_data(data: Any) -> Any:
    pass
```

### Google Style 文档字符串

```python
def get_user_by_id(user_id: int) -> Optional[User]:
    """根据用户 ID 获取用户信息。

    详细说明：此函数从数据库中查询指定 ID 的用户，
    如果用户不存在则返回 None。

    Args:
        user_id: 用户的唯一标识符

    Returns:
        User 对象如果找到，否则返回 None

    Raises:
        ValueError: 如果 user_id 小于 1

    Examples:
        >>> user = get_user_by_id(1)
        >>> print(user.name)
        'John Doe'
    """
    if user_id < 1:
        raise ValueError("user_id must be greater than 0")

    return session.get(User, user_id)
```

### Pydantic 模型

```python
from pydantic import BaseModel, Field, EmailStr
from typing import Optional

class UserBase(BaseModel):
    """用户基础模型。"""
    email: EmailStr = Field(..., description="用户邮箱")
    name: str = Field(..., min_length=1, max_length=100)

class UserCreate(UserBase):
    """用户创建模型。"""
    password: str = Field(..., min_length=8, description="密码")

class UserResponse(UserBase):
    """用户响应模型。"""
    id: int
    is_active: bool = True

    class Config:
        from_attributes = True
```

### 环境变量管理

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """应用配置。"""
    DATABASE_URL: str
    SECRET_KEY: str
    DEBUG: bool = False

    class Config:
        env_file = ".env"

settings = Settings()
```

```bash
# .env
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
SECRET_KEY=your-secret-key
DEBUG=True
```

---