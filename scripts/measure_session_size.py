"""Measure synthetic five-minute transcripts; never ingest child recordings."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import VivaFeedback, VivaSession
from app.db.session_repository import item_size_bytes, session_item


def main():
    """Print local synthetic size estimates without credentials or AWS calls.

    Hindi demonstrates why limits use UTF-8 bytes rather than character counts.
    These fixtures validate sizing assumptions, not real conversation lengths.
    """
    scenarios = {
        "english_750_words": "Plants need sunlight water and nutrients. " * 125,
        "hindi_750_words": "पौधों को पानी और प्रकाश चाहिए। " * 125,
        "english_2000_words_stress": "Plants need sunlight water and nutrients. " * 334,
    }
    for name, transcript in scenarios.items():
        session = VivaSession(
            user_id="synthetic-owner",
            student_name="Synthetic",
            title="Plants",
            topic="Plants",
            class_level="7",
            status="completed",
            transcript=transcript,
            feedback=VivaFeedback(score=8, summary="Synthetic result"),
        )
        item = session_item(session)
        conservative_bytes = item_size_bytes(item)
        print(
            json.dumps(
                {
                    "scenario": name,
                    "transcript_bytes": len(transcript.encode("utf-8")),
                    "item_bytes_upper_bound": conservative_bytes,
                }
            )
        )


if __name__ == "__main__":
    main()
