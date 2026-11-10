"""
Face Matching Service using FAISS (Facebook AI Similarity Search) & In-Memory TTL Debouncer.

FAISS provides ultra-fast vector similarity search:
- 1,000 employees → < 1ms search
- 10,000+ employees → < 3ms search
- Exact Cosine Similarity using Inner Product on L2-normalized 512-d ArcFace vectors.

Includes enterprise TTL Cache Debouncer to prevent duplicate attendance logs.
"""
import os
import time
import pickle
import threading
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
import numpy as np

from src.core.config import get_settings
from src.utils.logger import logger

settings = get_settings()


@dataclass
class MatchResult:
    """Result of a face matching operation."""
    employee_id: int
    confidence: float       # Cosine similarity score (0.0 to 1.0)
    distance: float         # 1.0 - confidence
    is_match: bool          # True if confidence >= threshold


class TTLFaceDebouncer:
    """
    In-memory Thread-Safe TTL Debouncer / Cooldown Manager.
    Prevents duplicate attendance logs for the same face within a configurable cooldown window.
    """
    def __init__(self, default_cooldown_seconds: float = 600.0):
        self._lock = threading.Lock()
        self.default_cooldown_seconds = default_cooldown_seconds
        # employee_id -> { "last_punch_ts": float, "last_punch_type": str, "punch_count": int }
        self._cache: Dict[int, Dict[str, any]] = {}

    def is_in_cooldown(self, employee_id: int, custom_cooldown: Optional[float] = None) -> Tuple[bool, float]:
        """
        Check if an employee is currently within the punch cooldown window.
        
        Returns:
            (is_blocked, remaining_seconds)
        """
        cooldown = custom_cooldown if custom_cooldown is not None else self.default_cooldown_seconds
        now = time.time()
        
        with self._lock:
            record = self._cache.get(employee_id)
            if not record:
                return False, 0.0
            
            elapsed = now - record["last_punch_ts"]
            if elapsed < cooldown:
                remaining = cooldown - elapsed
                return True, remaining
            return False, 0.0

    def record_punch(self, employee_id: int, punch_type: str = "CHECK_IN") -> None:
        """Record a successful punch and reset the TTL cooldown timer."""
        now = time.time()
        with self._lock:
            prev = self._cache.get(employee_id, {"punch_count": 0})
            self._cache[employee_id] = {
                "last_punch_ts": now,
                "last_punch_type": punch_type,
                "punch_count": prev.get("punch_count", 0) + 1
            }

    def reset_employee(self, employee_id: int) -> None:
        """Remove cooldown for a specific employee (e.g. manual reset)."""
        with self._lock:
            self._cache.pop(employee_id, None)

    def clear(self) -> None:
        """Clear all cooldown records."""
        with self._lock:
            self._cache.clear()


class FaceMatchingService:
    """
    FAISS-based Face Matching Engine (IndexFlatIP for exact Cosine Similarity).
    Supports multiple 512-d embeddings per employee (multi-angle registration).
    """

    def __init__(self):
        self._index = None
        self._id_map: Dict[int, int] = {}  # faiss_idx -> employee_id
        self._reverse_map: Dict[int, List[int]] = {}  # employee_id -> [faiss_indices]
        self._embedding_dim = 512  # ArcFace feature vector size
        self._index_path = os.path.join(settings.faiss_index_dir, "face_index.faiss")
        self._map_path = os.path.join(settings.faiss_index_dir, "id_map.pkl")
        self._lock = threading.Lock()
        
        # Debouncer instance (10 minutes default cooldown)
        self.debouncer = TTLFaceDebouncer(default_cooldown_seconds=600.0)

    def initialize(self):
        """Initialize or load the FAISS index from disk."""
        try:
            import faiss
        except ImportError:
            logger.error("FAISS package is required for high-speed vector matching.")
            raise

        with self._lock:
            if os.path.exists(self._index_path) and os.path.exists(self._map_path):
                self._load_index_locked()
            else:
                self._index = faiss.IndexFlatIP(self._embedding_dim)
                self._id_map = {}
                self._reverse_map = {}
                logger.info("Initialized fresh FAISS IndexFlatIP (dim=512, empty)")

            logger.info(f"FAISS index ready. Total vectors: {self._index.ntotal}, Total employees: {len(self._reverse_map)}")

    def _normalize(self, embedding: np.ndarray) -> np.ndarray:
        """L2-normalize an embedding vector to unit length for Cosine Similarity."""
        emb = embedding.astype(np.float32)
        norm = np.linalg.norm(emb)
        if norm > 1e-6:
            emb = emb / norm
        return emb

    def add_embedding(self, employee_id: int, embedding: np.ndarray) -> int:
        """
        Add a 512-d normalized face embedding to the FAISS index.
        Returns the new FAISS vector index.
        """
        if self._index is None:
            self.initialize()

        normed_emb = self._normalize(embedding).reshape(1, -1)

        with self._lock:
            faiss_idx = self._index.ntotal
            self._index.add(normed_emb)

            self._id_map[faiss_idx] = employee_id
            if employee_id not in self._reverse_map:
                self._reverse_map[employee_id] = []
            self._reverse_map[employee_id].append(faiss_idx)

        logger.debug(f"Added embedding for employee {employee_id} at FAISS idx {faiss_idx}")
        return faiss_idx

    def add_multi_embeddings(self, employee_id: int, embeddings: List[np.ndarray]) -> List[int]:
        """
        Batch add multiple pose embeddings for an employee (Center, Left, Right).
        """
        if not embeddings:
            return []
        
        if self._index is None:
            self.initialize()

        normed_list = [self._normalize(emb) for emb in embeddings if emb is not None]
        if not normed_list:
            return []

        matrix = np.vstack(normed_list).astype(np.float32)
        count = matrix.shape[0]

        with self._lock:
            start_idx = self._index.ntotal
            self._index.add(matrix)
            assigned_indices = []
            for i in range(count):
                curr_idx = start_idx + i
                self._id_map[curr_idx] = employee_id
                if employee_id not in self._reverse_map:
                    self._reverse_map[employee_id] = []
                self._reverse_map[employee_id].append(curr_idx)
                assigned_indices.append(curr_idx)

        logger.info(f"Added {count} multi-angle embeddings for employee {employee_id} to FAISS index.")
        return assigned_indices

    def search(self, embedding: np.ndarray, top_k: int = 1) -> List[MatchResult]:
        """
        Search for the top-k closest matching vectors in sub-millisecond latency.
        """
        if self._index is None or self._index.ntotal == 0:
            return []

        normed_query = self._normalize(embedding).reshape(1, -1)
        top_k = min(top_k, self._index.ntotal)

        with self._lock:
            similarities, indices = self._index.search(normed_query, top_k)

        results = []
        for sim, idx in zip(similarities[0], indices[0]):
            if idx < 0:
                continue

            emp_id = self._id_map.get(int(idx), -1)
            confidence = float(sim)
            threshold = settings.face_recognition_threshold

            results.append(MatchResult(
                employee_id=emp_id,
                confidence=confidence,
                distance=max(0.0, 1.0 - confidence),
                is_match=(confidence >= threshold),
            ))

        return results

    def identify(self, embedding: np.ndarray) -> Optional[MatchResult]:
        """
        Identify person from face embedding.
        Returns the best MatchResult if above threshold, otherwise None.
        """
        results = self.search(embedding, top_k=1)
        if results and results[0].is_match:
            return results[0]
        return None

    def remove_employee(self, employee_id: int) -> None:
        """
        Remove all embeddings for an employee and rebuild the compact FAISS index.
        """
        with self._lock:
            if employee_id not in self._reverse_map:
                return

            try:
                import faiss
            except ImportError:
                return

            remove_indices = set(self._reverse_map[employee_id])
            new_index = faiss.IndexFlatIP(self._embedding_dim)
            new_id_map = {}
            new_reverse_map = {}

            for old_idx in range(self._index.ntotal):
                if old_idx in remove_indices:
                    continue

                vec = self._index.reconstruct(old_idx)
                new_idx = new_index.ntotal
                new_index.add(vec.reshape(1, -1))

                emp_id = self._id_map[old_idx]
                new_id_map[new_idx] = emp_id
                if emp_id not in new_reverse_map:
                    new_reverse_map[emp_id] = []
                new_reverse_map[emp_id].append(new_idx)

            self._index = new_index
            self._id_map = new_id_map
            self._reverse_map = new_reverse_map
            self.debouncer.reset_employee(employee_id)

        logger.info(f"Removed employee {employee_id} from FAISS index. Remaining vectors: {self.total_embeddings}")

    def save_index(self) -> None:
        """Persist FAISS index and mappings to disk."""
        with self._lock:
            if self._index is None:
                return

            import faiss
            os.makedirs(os.path.dirname(self._index_path), exist_ok=True)
            faiss.write_index(self._index, self._index_path)
            with open(self._map_path, "wb") as f:
                pickle.dump({
                    "id_map": self._id_map,
                    "reverse_map": self._reverse_map,
                }, f)
            logger.info(f"FAISS index persisted ({self._index.ntotal} vectors)")

    def _load_index_locked(self) -> None:
        """Internal helper to load index under lock."""
        import faiss
        self._index = faiss.read_index(self._index_path)
        with open(self._map_path, "rb") as f:
            data = pickle.load(f)
            self._id_map = data["id_map"]
            self._reverse_map = data["reverse_map"]

    def load_index(self) -> None:
        """Public thread-safe method to load index."""
        with self._lock:
            self._load_index_locked()

    def rebuild_index(self, embeddings: Dict[int, List[np.ndarray]]) -> None:
        """Rebuild entire FAISS index from employee embeddings dict."""
        import faiss
        with self._lock:
            self._index = faiss.IndexFlatIP(self._embedding_dim)
            self._id_map = {}
            self._reverse_map = {}

            for employee_id, emb_list in embeddings.items():
                for emb in emb_list:
                    if emb is None:
                        continue
                    normed = self._normalize(emb).reshape(1, -1)
                    idx = self._index.ntotal
                    self._index.add(normed)
                    self._id_map[idx] = employee_id
                    if employee_id not in self._reverse_map:
                        self._reverse_map[employee_id] = []
                    self._reverse_map[employee_id].append(idx)

        logger.info(f"FAISS index rebuilt from DB with {self.total_embeddings} vectors across {self.total_employees} employees.")

    @property
    def total_embeddings(self) -> int:
        return self._index.ntotal if self._index else 0

    @property
    def total_employees(self) -> int:
        return len(self._reverse_map)


# Global singleton instance
face_matcher = FaceMatchingService()
