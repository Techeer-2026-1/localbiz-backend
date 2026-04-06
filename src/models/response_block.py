"""WebSocket 응답 블록 타입 정의 — Discriminated Union"""
from typing import Literal, Union, Any, List, Optional, Dict
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
    sub_category: Optional[str] = None
    address: Optional[str] = None
    district: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    phone: Optional[str] = None
    image_url: Optional[str] = None        # Google Places Photos API URL
    rating: Optional[float] = None
    is_open: Optional[bool] = None         # 현재 영업 여부 (Google Places 실시간)
    booking_url: Optional[str] = None
    naver_map_url: Optional[str] = None
    kakao_map_url: Optional[str] = None
    recommendation_reason: Optional[str] = None   # 추천 근거 문구


class PlaceBlock(BaseModel):
    type: Literal["place"] = "place"
    data: Place


class PlacesBlock(BaseModel):
    type: Literal["places"] = "places"
    data: List[Place]


class Event(BaseModel):
    event_id: str
    title: str
    category: str
    place_name: Optional[str] = None
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    price: Optional[str] = None
    poster_url: Optional[str] = None      # KOPIS/TourAPI 이미지 URL
    detail_url: Optional[str] = None


class EventsBlock(BaseModel):
    type: Literal["events"] = "events"
    data: List[Event]


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
    time: Optional[str] = None
    duration_min: Optional[int] = None
    walk_to_next_min: Optional[int] = None


class CourseBlock(BaseModel):
    type: Literal["course"] = "course"
    date: Optional[str] = None
    area: Optional[str] = None
    stops: List[CourseStop]


class MapMarkersBlock(BaseModel):
    type: Literal["map_markers"] = "map_markers"
    center: Dict[str, float]           # {"lat": 37.5, "lng": 127.0}
    zoom: int = 14
    markers: List[MapMarker]


class RouteStop(BaseModel):
    place_id: str
    name: str
    lat: float
    lng: float
    time: Optional[str] = None            # "10:00"
    duration_min: Optional[int] = None    # 체류 시간(분)
    walk_to_next_min: Optional[int] = None


class MapRouteBlock(BaseModel):
    type: Literal["map_route"] = "map_route"
    stops: List[RouteStop]
    polyline: Optional[List[List[float]]] = None  # [[lat, lng], ...]


class ChartBlock(BaseModel):
    type: Literal["chart"] = "chart"
    chart_type: str   # "bar" | "radar" | "line"
    title: Optional[str] = None
    data: List[Dict[str, Any]]
    keys: List[str]   # recharts dataKey 목록


class CalendarResult(BaseModel):
    event_id: Optional[str] = None
    title: str
    datetime: str
    location: Optional[str] = None
    status: str = "created"           # "created" | "failed"


class CalendarBlock(BaseModel):
    type: Literal["calendar"] = "calendar"
    data: CalendarResult


class Reference(BaseModel):
    title: str
    link: str
    postdate: Optional[str] = None
    source: Optional[str] = None


class ReferencesBlock(BaseModel):
    type: Literal["references"] = "references"
    data: List[Reference]


class AnalysisSourcesBlock(BaseModel):
    type: Literal["analysis_sources"] = "analysis_sources"
    place_name: str
    review_count: Optional[int] = None
    sources: Optional[Dict[str, int]] = None
    sample_reviews: Optional[List[str]] = None


class FavoritesBlock(BaseModel):
    type: Literal["favorites"] = "favorites"
    data: List[Place]
    action: str = "list"               # "list" | "added" | "removed"


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
