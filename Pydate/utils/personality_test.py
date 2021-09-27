from django.contrib.auth.models import User

from ..models import PersonalityTestItem, PersonalityTestAnswer


def get_personality_type(user_id):
    user = User.objects.get(pk=user_id)
    answers = [answer.answer for answer in PersonalityTestAnswer.objects.filter(user=user_id)]
    test_items_info = PersonalityTestItem.objects.all()

    result_type = get_personality_trait("IE", answers)
    result_type += get_personality_trait("SN", answers)
    result_type += get_personality_trait("FT", answers)
    result_type += get_personality_trait("JP", answers)

    return result_type


def get_personality_trait(trait_type, answers):
    items = PersonalityTestItem.objects.all().filter(type=trait_type)
    score = 0
    subtraction_count = 0

    for item in items:
        if item.inversion:
            score -= answers[item.itemID]
            subtraction_count += 1
        else:
            score += answers[item.itemID]

    threshold_score = (len(items) * 6) // 2 - subtraction_count * 6

    if score > threshold_score:
        return trait_type[1]
    else:
        return trait_type[0]
