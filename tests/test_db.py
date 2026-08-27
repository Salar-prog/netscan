from sqlalchemy import create_engine, event


def test_busy_timeout_applied_per_connection():
    """Verify the connect-event listener sets busy_timeout on every new connection."""
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False})

    @event.listens_for(test_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    with test_engine.connect() as conn:
        result = conn.exec_driver_sql("PRAGMA busy_timeout").scalar()
        assert result == 5000
