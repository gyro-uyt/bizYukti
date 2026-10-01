import io

from PIL import Image

from app import taxonomy
from app.models import Property
from app.security import utcnow
from app.services import matching, media

from .conftest import photo


def test_classifier_understands_english_and_hindi_terms():
    assert taxonomy.classify("We need a medical store near the park")[0] == "pharmacy"
    assert taxonomy.classify("kirana shop")[0] == "grocery"
    assert taxonomy.classify("dawai ki dukaan")[0] == "pharmacy"
    assert taxonomy.classify("something nice")[0] == "other"


def test_clean_title_strips_request_phrasing():
    assert taxonomy.clean_title("I want a bookstore near the park") == "Bookstore near the park"
    assert taxonomy.clean_title("please we need a pharmacy!") == "Pharmacy"


def test_space_fit_rules():
    assert taxonomy.suitability("pharmacy", "shop", 850) == (1.0, 1.0)
    assert taxonomy.suitability("pharmacy", "land", 850) == (0.0, 0.0)
    assert taxonomy.suggest_property_type(4000) == "warehouse"
    assert taxonomy.suggest_property_type(300, "small office on first floor") == "office"


def test_match_score_explains_itself():
    prop = Property(type="shop", size_sqft=850, availability="now", last_confirmed_at=utcnow(),
                    verification_status="verified")
    res = matching.score_pair("pharmacy", prop, {"supporters": 184, "demands": 1, "lat": 0, "lng": 0}, 1300)
    assert res["score"] >= 90
    assert res["summary"] == ("Matched because 184 nearby residents requested a pharmacy and this shop "
                              "is within 1.3 km of the demand cluster.")
    assert "850 sq ft fits a typical pharmacy (150–1,000 sq ft)" in res["reasons"]
    assert matching.score_pair("pharmacy", Property(type="land", size_sqft=5000), {"supporters": 1, "lat": 0, "lng": 0}, 10) is None


def test_blur_and_duplicate_detection_calibration():
    sharp, blurred = Image.open(io.BytesIO(photo(1))), Image.open(io.BytesIO(photo(1, blur=8)))
    assert media.blur_score(sharp) > media.BLUR_THRESHOLD > media.blur_score(blurred)
    same = Image.open(io.BytesIO(photo(1)))
    other = Image.open(io.BytesIO(photo(2)))
    assert media.hamming(media.dhash(sharp), media.dhash(same)) <= media.DUP_DISTANCE
    assert media.hamming(media.dhash(sharp), media.dhash(other)) > media.DUP_DISTANCE
