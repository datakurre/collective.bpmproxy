"""Timeline (edit-decision list) schema v2: load, validate, and write.

A timeline is the *only* input the composer (screencast.compose) and the
verifier (screencast.verify) need. It records, for one take:

- the observer clip that spans the whole take;
- one entry per recorded actor turn, with its measured start offset on the
  observer's own clock;
- a chronological list of edit events (turn_start/turn_end, chapter, focus,
  hold, caption) carrying real timestamps taken from keyword start/end
  times, not values computed and immediately discarded by the recording
  run.

See scripts/screencast/schema/timeline.schema.json for the JSON Schema this
module validates against, and its field-level documentation.
"""

from pathlib import Path
import copy
import json


VERSION = 2

SCHEMA_PATH = Path(__file__).with_name("schema") / "timeline.schema.json"

EVENT_TYPES = frozenset(
    {"turn_start", "turn_end", "chapter", "focus", "hold", "caption", "wait"}
)

# Back-to-back turns can leave a near-zero real-time gap, where ffprobe's
# measured clip duration and the wall-clock offsets recorded via
# time.monotonic() disagree by a small amount (video encoder startup
# latency), not an actual ordering problem. The composer clamps a gap
# narrower than this instead of failing the whole take; only a larger
# overlap -- which would mean two actor turns genuinely ran concurrently --
# is treated as a real bug in the recording, not the edit.
OVERLAP_TOLERANCE = 1.5


class TimelineError(ValueError):
    """An invalid or unsupported timeline document."""


def _load_schema():
    return json.loads(SCHEMA_PATH.read_text())


def validate(data):
    """Validate `data` (a decoded timeline document) against the schema.

    Raises TimelineError with a readable message on the first violation;
    does nothing (returns None) when the document is valid. jsonschema is
    imported lazily so the rest of this module -- and the composer/verifier
    logic that does not need re-validation -- has no hard dependency on it
    at import time.
    """
    version = data.get("version") if isinstance(data, dict) else None
    if version != VERSION:
        raise TimelineError(
            f"Unsupported timeline version {version!r}; this composer/verifier "
            f"only understands version {VERSION}."
        )
    try:
        import jsonschema
    except ImportError as error:
        raise TimelineError(
            "jsonschema is required to validate timeline documents "
            "(pip install jsonschema)"
        ) from error
    validator_cls = jsonschema.validators.validator_for(_load_schema())
    validator = validator_cls(_load_schema())
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        path = "/".join(str(part) for part in first.path) or "<root>"
        raise TimelineError(f"Invalid timeline at {path}: {first.message}")


class Timeline:
    """In-memory timeline document, with typed accessors over the raw dict.

    Keep the raw dict as the source of truth (`.data`) rather than mirroring
    every field onto attributes: the composer and verifier only ever need a
    handful of derived views (events by type, actor clips by name), and a
    thin wrapper keeps `to_json()` a lossless round-trip even for fields a
    future schema minor-version adds that this code does not know about yet.
    """

    def __init__(self, data):
        validate(data)
        self.data = data

    @classmethod
    def new(cls, observer_video, observer_name="observer"):
        return cls(
            {
                "version": VERSION,
                "observer": {"name": observer_name, "video": str(observer_video)},
                "actors": [],
                "events": [],
            }
        )

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text()))

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.data, indent=2, sort_keys=False) + "\n")
        return path

    def to_json(self):
        return json.dumps(self.data, indent=2, sort_keys=False)

    @property
    def observer(self):
        return self.data["observer"]

    @property
    def actors(self):
        return self.data["actors"]

    @property
    def events(self):
        return self.data["events"]

    def events_of(self, event_type):
        if event_type not in EVENT_TYPES:
            raise TimelineError(f"Unknown event type {event_type!r}")
        return [event for event in self.events if event["type"] == event_type]

    def actor_clip(self, name):
        for clip in self.actors:
            if clip["actor"] == name:
                return clip
        raise TimelineError(f"No actor clip named {name!r} on this timeline")

    def add_actor_clip(self, actor, video, offset, duration=None):
        clip = {"actor": actor, "video": str(video), "offset": offset}
        if duration is not None:
            clip["duration"] = duration
        self.data["actors"].append(clip)
        return clip

    def add_event(self, event):
        if event.get("type") not in EVENT_TYPES:
            raise TimelineError(f"Unknown event type {event.get('type')!r}")
        self.data["events"].append(event)
        return event

    def copy(self):
        return Timeline(copy.deepcopy(self.data))
