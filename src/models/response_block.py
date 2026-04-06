"""WebSocket 응답 블록 타입 정의 — Discriminated Union"""

from typing import Any, Literal, Union

from pydantic import BaseModel


class IntentBlock(BaseModel):
    type: Literal["intent"] = "intent"
    value: str


class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    content: str


class TextStreamBlock(BaseModel):
    type: Literal["text_stream"] = "text_stream"
    system: str = ""
    prompt: str = ""


class Place(BaseModel):
    place_id: str
    name: str
    category: str
    sub_category: str | None = None
    address: str | None = None
    district: str | None = None
    lat: float | None = None
    lng: float | None = None
    phone: str | None = None
    image_url: str | None = None  # Google Places Photos API URL
    rating: float | None = None
    is_open: bool | None = None  # 현재 영업 여부 (Google Places 실시간)
    booking_url: str | None = None
    naver_map_url: str | None = None
    kakao_map_url: str | None = None
    recommendation_reason: str | None = None  # 추천 근거 문구


class PlaceBlock(BaseModel):
    type: Literal["place"] = "place"
    data: Place


class PlacesBlock(BaseModel):
    type: Literal["places"] = "places"
    data: list[Place]


class Event(BaseModel):
    event_id: str
    title: str
    category: str
    place_name: str | None = None
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    date_start: str | None = None
    date_end: str | None = None
    price: str | None = None
    poster_url: str | None = None  # KOPIS/TourAPI 이미지 URL
    detail_url: str | None = None


class EventsBlock(BaseModel):
    type: Literal["events"] = "events"
    data: list[Event]


class MapMarker(BaseModel):
    place_id: str
    name: str
    lat: float
    lng: float
    category: str


class CourseStop(BaseModel):
    order: int
    place_id: str
    name: str
    category: str
    lat: float
    lng: float
    time: str | None = None
    duration_min: int | None = None
    walk_to_next_min: int | None = None


class CourseBlock(BaseModel):
    type: Literal["course"] = "course"
    date: str | None = None
    area: str | None = None
    stops: list[CourseStop]


class MapMarkersBlock(BaseModel):
    type: Literal["map_markers"] = "map_markers"
    center: dict[str, float]  # {"lat": 37.5, "lng": 127.0}
    zoom: int = 14
    markers: list[MapMarker]


class RouteStop(BaseModel):
    place_id: str
    name: str
    lat: float
    lng: float
    time: str | None = None  # "10:00"
    duration_min: int | None = None  # 체류 시간(분)
    walk_to_next_min: int | None = None


class MapRouteBlock(BaseModel):
    type: Literal["map_route"] = "map_route"
    stops: list[RouteStop]
    polyline: list[list[float]] | None = None  # [[lat, lng], ...]


class ChartBlock(BaseModel):
    type: Literal["chart"] = "chart"
    chart_type: str  # "bar" | "radar" | "line"
    title: str | None = None
    data: list[dict[str, Any]]
    keys: list[str]  # recharts dataKey 목록


class CalendarResult(BaseModel):
    event_id: str | None = None
    title: str
    datetime: str
    location: str | None = None
    status: str = "created"  # "created" | "failed"


class CalendarBlock(BaseModel):
    type: Literal["calendar"] = "calendar"
    data: CalendarResult


class Reference(BaseModel):
    title: str
    link: str
    postdate: str | None = None
    source: str | None = None


class ReferencesBlock(BaseModel):
    type: Literal["references"] = "references"
    data: list[Reference]


class AnalysisSourcesBlock(BaseModel):
    type: Literal["analysis_sources"] = "analysis_sources"
    place_name: str
    review_count: int | None = None
    sources: dict[str, int] | None = None
    sample_reviews: list[str] | None = None


class FavoritesBlock(BaseModel):
    type: Literal["favorites"] = "favorites"
    data: list[Place]
    action: str = "list"  # "list" | "added" | "removed"


class DoneBlock(BaseModel):
    type: Literal["done"] = "done"


class ErrorBlock(BaseModel):
    type: Literal["error"] = "error"
    message: str


ResponseBlock = Union[
    IntentBlock,
    TextBlock,
    TextStreamBlock,
    PlaceBlock,
    PlacesBlock,
    EventsBlock,
    CourseBlock,
    MapMarkersBlock,
    MapRouteBlock,
    ChartBlock,
    CalendarBlock,
    ReferencesBlock,
    AnalysisSourcesBlock,
    FavoritesBlock,
    DoneBlock,
    ErrorBlock,
]
