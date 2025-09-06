#!/usr/bin/env python3

import sqlite3
import uuid
from collections.abc import MutableMapping
from typing import Iterator


class SQLiteCache(MutableMapping[str, str]):
    """A persistent key-value cache backed by SQLite.

    `SQLiteCache` provides a dict-like interface for storing string key-value
    pairs in an `sqlite3` database.
    It fully implements the `collections.abc.MutableMapping` protocol, allowing
    it to be used anywhere a dictionary is expected while providing persistent
    storage across program runs.

    The cache creates a single table with a constraint to ensure unique keys.
    All operations are immediately committed to disk for durability.

    Args:
        database: Path to the database file, or `":memory:"` for in-memory storage.
                  The database and table will be created if they don't exist.

    Attributes:
        database: The database path provided during initialization.

    Examples:
        Basic dictionary-like operations::

        >>> cache = SQLiteCache(":memory:")
        >>> cache["key1"] = "value1"
        >>> cache["key2"] = "value2"
        >>> cache["key1"]
        'value1'
        >>> "key1" in cache
        True
        >>> len(cache)
        2

        Iteration and dict methods::

        >>> cache = SQLiteCache(":memory:")
        >>> cache.update({"a": "1", "b": "2", "c": "3"})
        >>> sorted(cache.keys())
        ['a', 'b', 'c']
        >>> sorted(cache.values())
        ['1', '2', '3']
        >>> list(cache.items())
        [('a', '1'), ('b', '2'), ('c', '3')]

        Error handling::

        >>> cache = SQLiteCache(":memory:")
        >>> cache["nonexistent"]
        Traceback (most recent call last):
        KeyError: 'nonexistent'
        >>> del cache["nonexistent"]
        Traceback (most recent call last):
        KeyError: 'nonexistent'

    Note:
        All write operations are immediately committed to the database for durability.
        Each operation opens and closes its own database connection for thread safety.
        For in memory databases, a shared cache is used to persist data between calls.
    """

    def __init__(self, database: str) -> None:
        self.database = database

        # For :memory: databases, use shared cache to persist data across calls
        if database == ":memory:":
            self.database = f"file:{uuid.uuid4()}?mode=memory&cache=shared"

        with sqlite3.connect(self.database, uri=True) as connection:
            query = (
                "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT)"
            )
            connection.execute(query)
            connection.commit()

    def __getitem__(self, key: str) -> str:
        with sqlite3.connect(self.database, uri=True) as connection:
            query = "SELECT value FROM cache WHERE key = ?"
            cursor = connection.execute(query, (key,))
            row = cursor.fetchone()
            if row is None:
                raise KeyError(key)
            return row[0]

    def __setitem__(self, key: str, value: str) -> None:
        with sqlite3.connect(self.database, uri=True) as connection:
            query = "INSERT OR REPLACE INTO cache VALUES (?, ?)"
            connection.execute(query, (key, value))
            connection.commit()

    def __delitem__(self, key: str) -> None:
        with sqlite3.connect(self.database, uri=True) as connection:
            query = "DELETE FROM cache WHERE key = ? RETURNING value"
            cursor = connection.execute(query, (key,))
            row = cursor.fetchone()
            if row is None:
                raise KeyError(key)
            connection.commit()

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        with sqlite3.connect(self.database, uri=True) as connection:
            query = "SELECT 1 FROM cache WHERE key = ? LIMIT 1"
            cursor = connection.execute(query, (key,))
            row = cursor.fetchone()
            return row is not None

    def __iter__(self) -> Iterator[str]:
        with sqlite3.connect(self.database, uri=True) as connection:
            query = "SELECT key FROM cache"
            cursor = connection.execute(query)
            for row in cursor:
                yield row[0]

    def __len__(self) -> int:
        with sqlite3.connect(self.database, uri=True) as connection:
            query = "SELECT COUNT(*) FROM cache"
            cursor = connection.execute(query)
            row = cursor.fetchone()
            return row[0]
