"""Easy Quant 首个数据库结构基线。"""

from alembic import op

from easy_quant.infrastructure.persistence.base import Base
from easy_quant.infrastructure.persistence.models.audit import AuditEventModel
from easy_quant.infrastructure.persistence.models.backtesting import (
    BacktestMetricModel,
    BacktestPeriodModel,
    BacktestRunModel,
    DataSnapshotChunkModel,
    DataSnapshotModel,
    SimulatedTradeModel,
)
from easy_quant.infrastructure.persistence.models.identity import (
    InvitationModel,
    SessionModel,
    UserModel,
)
from easy_quant.infrastructure.persistence.models.live_tracking import (
    LiveInstanceModel,
    RecommendationModel,
)
from easy_quant.infrastructure.persistence.models.market_data_catalog import (
    AcquisitionRunModel,
    DatasetModel,
    DataSourceModel,
    RawCacheModel,
    SourceAttemptModel,
    SourceBindingModel,
)
from easy_quant.infrastructure.persistence.models.market_data_records import (
    DailyBarModel,
    InstrumentModel,
    JsonMarketRecordModel,
    TradingDayModel,
)
from easy_quant.infrastructure.persistence.models.notifications import (
    NotificationDeliveryModel,
    NotificationSubscriptionModel,
)
from easy_quant.infrastructure.persistence.models.portfolio_ledger import (
    ActualOperationModel,
    PortfolioLedgerEntryModel,
)
from easy_quant.infrastructure.persistence.models.runtime_state import RuntimeDocumentModel
from easy_quant.infrastructure.persistence.models.scheduling import JobModel, ScheduledTaskModel
from easy_quant.infrastructure.persistence.models.strategies import (
    StrategyModel,
    StrategyVersionModel,
)

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

# 固定本次基线包含的模型，避免导入被格式化工具误删。
_SCHEMA_MODELS = (
    AuditEventModel,
    UserModel,
    InvitationModel,
    SessionModel,
    DatasetModel,
    DataSourceModel,
    SourceBindingModel,
    RawCacheModel,
    AcquisitionRunModel,
    SourceAttemptModel,
    DailyBarModel,
    InstrumentModel,
    TradingDayModel,
    JsonMarketRecordModel,
    StrategyModel,
    StrategyVersionModel,
    DataSnapshotModel,
    DataSnapshotChunkModel,
    BacktestRunModel,
    BacktestPeriodModel,
    SimulatedTradeModel,
    BacktestMetricModel,
    LiveInstanceModel,
    RecommendationModel,
    NotificationSubscriptionModel,
    NotificationDeliveryModel,
    ActualOperationModel,
    PortfolioLedgerEntryModel,
    JobModel,
    ScheduledTaskModel,
    RuntimeDocumentModel,
)


def upgrade() -> None:
    """在全新空数据库中创建当前完整结构。"""

    assert _SCHEMA_MODELS
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=False)


def downgrade() -> None:
    """删除本基线创建的全部业务表。"""

    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=False)
