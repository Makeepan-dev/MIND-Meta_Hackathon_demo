import sqlite3
import os
import time
import json
from colorama import Fore
import config

def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        try:
            print(text.encode("ascii", errors="replace").decode("ascii"))
        except Exception:
            pass

class MemoryAgent:
    def __init__(self):
        _default_assets = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets")
        _assets_dir = getattr(config, "ASSETS_DIR", _default_assets)
        os.makedirs(_assets_dir, exist_ok=True)
        self.db_path = os.path.join(_assets_dir, "mind_memory.db")
        self._init_db()

    def _init_db(self):
        """Creates the messages table if it doesn't exist."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL
                )
            ''')
            conn.commit()
            conn.close()
            conn.close()
            
            # OPTIMIZATION: Enable WAL Mode (Write-Ahead Logging)
            # This allows concurrent reads and writes, preventing UI freezes.
            conn = sqlite3.connect(self.db_path)
            conn.execute('PRAGMA journal_mode=WAL;')
            conn.execute('PRAGMA synchronous=NORMAL;')
            conn.close()
            
            _safe_print(f"{Fore.GREEN}🧠 [MEMORY] Cortex Database Connected (WAL Mode).")
        except Exception as e:
            _safe_print(f"{Fore.RED}🧠 [MEMORY] Init Error: {e}")

    def save_message(self, role, content):
        """Saves a message to the database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('INSERT INTO conversation_history (role, content, timestamp) VALUES (?, ?, ?)', 
                           (role, content, time.time()))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Memory Save Error: {e}")

    def get_recent_context(self, limit=10):
        """Retrieves the last N messages formatted for the LLM."""
        context = []
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            # Get last N messages ordered by time
            cursor.execute('''
                SELECT role, content FROM conversation_history 
                ORDER BY id DESC LIMIT ?
            ''', (limit,))
            rows = cursor.fetchall()
            conn.close()
            
            # Reverse to chronological order (Oldest -> Newest)
            for row in reversed(rows):
                context.append({"role": row[0], "content": row[1]})
                
        except Exception as e:
            print(f"Memory Retrieval Error: {e}")
            
        return context

    def search_memory(self, query, limit=3):
        """Searches past conversations for relevant keywords."""
        results = []
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Simple keyword matching (improve with FTS later if needed)
            # Remove common stop words for better effective search if really needed, 
            # but for now, we'll search for the whole phrase or parts.
            # Actually, splitting by words is better for a naive search
            
            keywords = [w for w in query.split() if len(w) > 4] # Only meaningful words
            if not keywords:
                 keywords = [query]
            
            # Construct a dynamic query
            # We want rows where content matches ANY keyword 
            # (OR logic, ranked by number of matches would be ideal, but simple OR is fine)
            
            where_clauses = []
            params = []
            for word in keywords:
                where_clauses.append("content LIKE ?")
                params.append(f"%{word}%")
            
            if not where_clauses:
                return []
                
            sql = f'''
                SELECT role, content, timestamp FROM conversation_history 
                WHERE ({' OR '.join(where_clauses)})
                ORDER BY id DESC LIMIT ?
            '''
            params.append(limit)
            
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            conn.close()
            
            for row in rows:
                results.append(f"[{row[0].upper()}]: {row[1]}")
                
        except Exception as e:
            print(f"Memory Search Error: {e}")
            
        return results

    def clear_memory(self):
        """Wipes the conversation history."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM conversation_history')
            conn.commit()
            conn.close()
            print(f"{Fore.YELLOW}🧠 [MEMORY] Cortex Wiped.")
        except Exception as e:
            print(f"Memory Wipe Error: {e}")
