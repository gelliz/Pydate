import json
import urllib.request

from django.contrib.auth import authenticate, login
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in
from django.db.models import Q
from django.dispatch import receiver
from django.forms import formset_factory
from django.http import JsonResponse
from django.http.response import HttpResponseNotFound
from django.shortcuts import get_object_or_404
from django.shortcuts import render, redirect
from django.utils.datastructures import MultiValueDictKeyError
from django.views.decorators.http import require_http_methods

from Chat.models import UserChat
from Pydate import settings
from Pydate.forms import RegisterForm, PersonalQuestionsForm, PersonalQuestionsCreateForm, RemainForm
from Pydate.models import PersonalityTestItem, PersonalityTestAnswer
from Pydate.models import UserData, PersonalQuestionUser, PersonalQuestionContent, PersonalQuestionAnswer, Match, \
    UserLog
from functions import choose_best_by_personality, send_email, calculate_age, distance_between, get_client_ip, \
    have_i_question, generate_pass
from .utils.personality_test import get_personality_type


@login_required
@require_http_methods(["POST"])
def update_profile_picture(request):
    file = request.FILES.get('image')
    user = request.user
    user = UserData.objects.get(user=user)
    user.photo = file
    user.save()
    return JsonResponse({'message': 'success'}, status=200)


@login_required
@require_http_methods(["POST"])
def update_profile(request):
    user = request.user
    if user.check_password(request.POST['password']):
        data = request.POST
        user_data = UserData.objects.filter(user=user)[0]
        user.first_name = data['first_name']
        user.last_name = data['last_name']
        user.email = data['email']
        user_data.sex = data['sex']
        user_data.birth = data['birth']
        user_data.description = data['description']
        user_data.searching_for = data['looking_for']
        user.save()
        user_data.save()
        return JsonResponse({'message': 'success'}, status=200)
    else:
        return JsonResponse({'message': 'Wrong password!'}, status=400)


@login_required
@require_http_methods(["GET"])
def profile(request):
    user = request.user
    user_data = UserData.objects.filter(user=user)[0]
    data = {
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
        'birth': user_data.birth,
        'description': user_data.description,
        'sex': user_data.sex,
        'looking_for': user_data.searching_for
    }
    try:
        data['url'] = user_data.photo.url
    except ValueError:
        data['url'] = False
    return render(request, 'html_pages/profile_editor.html', {'data': data})


def base(request):
    if request.user.is_authenticated:
        return render(request, 'html_pages/view_people.html', {})
    return render(request, 'html_pages/base.html', {})


@require_http_methods(["GET", "POST"])
def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            user.refresh_from_db()
            prof = UserData(user=user)
            prof.birth = form.cleaned_data.get('birth_date')
            prof.sex = form.cleaned_data.get('sex')
            prof.searching_for = form.cleaned_data.get('searching_for')
            prof.save()
            log = UserLog(user=user)
            log.save()
            raw_password = form.cleaned_data.get('password1')
            user = authenticate(username=user.username, password=raw_password)
            login(request, user)
            first_item_id = PersonalityTestItem.objects.order_by('itemID')[0].itemID
            context = {'first_item_id': first_item_id}
            return render(request, 'html_pages/personality_test.html', context)
    else:
        form = RegisterForm()
    return render(request, 'html_pages/register.html', {'form': form})


# def login_view(request):
#     if request.method == 'POST':
#         username = request.POST['username']
#         password = request.POST['password']
#         user = authenticate(username=username, password=password)
#         if user is not None:
#             login(request, user)
#
#         else:
#             return redirect('html_pages/login.html')
#     return render(request, 'html_pages/login')

def personality_test(request):
    first_item_id = PersonalityTestItem.objects.order_by('itemID')[0].itemID
    context = {'first_item_id': first_item_id}
    return render(request, 'html_pages/personality_test.html', context)


def test_vote(request, test_item_id):
    test_item = get_object_or_404(PersonalityTestItem, pk=test_item_id)
    if request.method == "POST":
        ans, creation = PersonalityTestAnswer.objects.get_or_create(itemID=test_item, user=request.user)
        try:
            ans.answer = request.POST['choice']
            ans.save()
        except (KeyError, MultiValueDictKeyError):
            return render(request, 'html_pages/test_choice.html',
                          {'test_item': test_item, 'error_message': "You didn't select a choice!"})

        if PersonalityTestItem.objects.filter(pk=test_item_id + 1).exists():
            next_test_item = PersonalityTestItem.objects.get(pk=test_item_id + 1)
            return render(request, 'html_pages/test_choice.html', {'test_item': next_test_item})
        else:
            user = UserData.objects.get(user_id=request.user.id)
            user.personality = get_personality_type(user.user.id)
            user.save()
            return render(request, 'html_pages/test_summary.html')
    else:
        return render(request, 'html_pages/test_choice.html', {'test_item': test_item})


def logout_view(request):
    logout(request)
    return render(request, 'html_pages/base.html', {})


def info_view(request):
    return render(request, 'html_pages/view_info.html', {})


@login_required
def personal_questionnaire(request, username):
    question_user = User.objects.get(username=username)
    match = Match.objects.filter(user1=request.user, user2=question_user)
    if not match:
        match = Match.objects.filter(user1=question_user, user2=request.user)
        if not match:
            return redirect("/")
        # question_user = request.user  # to replace with the upper line
    questions = []
    questions_ids = []
    personal_questions_user = PersonalQuestionUser.objects.filter(user=question_user)
    if personal_questions_user:
        for p in personal_questions_user:
            answer = PersonalQuestionAnswer.objects.filter(user=request.user, questionID=p.questionID)
            if answer:
                return redirect('/')
            queryset = PersonalQuestionContent.objects.filter(questionID=str(p.questionID_id)).values("content").all()
            if queryset:
                questions += [q["content"] for q in queryset]
                questions_ids.append(str(p.questionID_id))
    formset_form = formset_factory(PersonalQuestionsForm, extra=len(questions_ids))
    if request.method == "POST":
        formset = formset_form(request.POST)
        if formset.is_valid():
            for i, form in enumerate(formset):
                if form.is_valid():
                    answer = form.save(commit=False)
                    answer.user = request.user
                    answer.questionID = personal_questions_user[i].questionID
                    answer.content = form.cleaned_data.get("content")
                    answer.save()
            return redirect('/')
    else:
        formset = formset_form()
    return render(request, 'html_pages/personal_questionnaire.html',
                  {"username": username, "formset": formset, "questions": questions})


@login_required
def my_matches(request):
    matches_data = []
    # search matches for user1=request.user
    matches = Match.objects.filter(user1=request.user)
    if matches:
        for match in matches:
            if (match.chatting_match == "11" and not (
                    match.personal_questions_match == "11" or match.personal_questions_match == "10")):
                u = UserData.objects.get(user=match.user2)
                if u.photo:
                    matches_data.append({"username": u.user.username, "description": u.description, "photo": u.photo})
                else:
                    matches_data.append({"username": u.user.username, "description": u.description,
                                         "photo": "images/user_profile_pictures/default.jpg/"})

    # search matches for user2=request.user
    matches = Match.objects.filter(user2=request.user)
    if matches:
        for match in matches:
            if (match.chatting_match == "11" and not (
                    match.personal_questions_match == "11" or match.personal_questions_match == "01")):
                u = UserData.objects.get(user=match.user1)
                if u.photo:
                    matches_data.append({"username": u.user.username, "description": u.description, "photo": u.photo})
                else:
                    matches_data.append({"username": u.user.username, "description": u.description,
                                         "photo": "images/user_profile_pictures/default.jpg/"})
    if len(matches_data) == 0:
        display_no_matches_info = True
    else:
        display_no_matches_info = False

    return render(request, 'html_pages/my_matches.html',
                  {"matches_data": matches_data, "display_no_matches_info": display_no_matches_info,
                   'media_url': settings.STATIC_URL})


@login_required
def view_answers(request):
    # here is the element that I will return
    questions = []
    descriptions = []
    photos = []
    users_ids = []
    users_index = []
    ages = []
    question_content = []
    locations = []
    # not here anymore
    personal_questions_user = PersonalQuestionUser.objects.filter(user=request.user)
    mydata = UserData.objects.get(user=request.user)
    if not mydata.personality:
        display = False
    else:
        display = True
        if personal_questions_user:
            for p in personal_questions_user:
                answer_set = PersonalQuestionAnswer.objects.filter(questionID=str(p.questionID))
                question_set = PersonalQuestionContent.objects.filter(questionID=str(p.questionID)).values("content").all()
                if answer_set:
                    for usr in answer_set:
                        if str(usr.user) not in users_ids:
                            questions += [[str(usr.content)]]

                            users_ids += [(str(usr.user))]
                            question_content += [[q["content"] for q in question_set]]
                            # location
                            locations += [float("{0:.2f}".format(distance_between(usr.user, request.user)))]

                            # sets
                            user_set = UserData.objects.filter(user=str(usr.user.id)).values("id", "description",
                                                                                             "photo",
                                                                                             "birth").all()
                            user_set2 = UserData.objects.filter(user=str(usr.user.id)).values("user_id").all()
                            # data from sets
                            descriptions += [' ' + q["description"] for q in user_set]
                            photos += [q["photo"] for q in user_set]
                            ages += [calculate_age(q["birth"]) for q in user_set]
                            users_index += [(q["user_id"]) for q in user_set2]
                        else:
                            for idu, u in enumerate(users_ids):
                                if str(usr.user) == u:
                                    questions[idu] += [(str(usr.content))]
                                    question_content[idu] += [q["content"] for q in question_set]

    formset_form = formset_factory(PersonalQuestionsForm, extra=len(users_ids))
    if len(users_ids) == 0:
        display = False
    formset = formset_form()
    return render(request, 'html_pages/view_answers.html',
                  {"display": display, "formset": formset, "question_content": question_content, "names": users_ids,
                   "user_index": users_index, "descriptions": descriptions, "questions": questions, "age": ages,
                   "img": photos, "local": locations, 'media_url': settings.STATIC_URL})


def questions_delete(us1, us2):
    personal_questions_user = PersonalQuestionUser.objects.filter(user=us1)
    if personal_questions_user:
        for ques in personal_questions_user:
            PersonalQuestionAnswer.objects.filter(user=us2, questionID=ques.questionID).delete()


def match_decline(user1, user_id):
    comrade = User.objects.get(id=str(user_id))
    questions_delete(user1, comrade)  # deleting friendly answers to questions from authorized users
    questions_delete(comrade, user1)  # conversely (vice versa)
    # changed matches to AGREE_NONE
    match = Match.objects.filter(user1=user1, user2=comrade)
    if match:
        match[0].chatting_match = Match.Agreement.AGREE_NONE
        match[0].save()
        return
    else:
        match = Match.objects.filter(user2=user1, user1=comrade)
        if match:
            match[0].chatting_match = Match.Agreement.AGREE_NONE
            match[0].save()
            return

    # If there was no matcha then I do it and set it on AGREE_NONE
    if match:
        match.save()
    else:
        if user1.username < comrade.username:
            match = Match.objects.create(user1=user1, user2=comrade, chatting_match=Match.Agreement.AGREE_1_TO_2)
        else:
            match = Match.objects.create(user2=user1, user1=comrade, chatting_match=Match.Agreement.AGREE_2_TO_1)
        match.save()


def match_delete(request, user_id=None):
    match_decline(request.user, user_id)
    return redirect("view_answers")


def match_accept(request, user_id=None):
    comrade = User.objects.get(id=str(user_id))
    match = Match.objects.filter(user1=request.user, user2=comrade)
    if match:
        if len(match) > 1:
            return HttpResponseNotFound(
                '<h1>Error. There are 2 same matches in the database. Contact the administration. </h1>')
        m = match[0]
        if m.personal_questions_match == Match.Agreement.AGREE_2_TO_1:
            m.personal_questions_match = Match.Agreement.AGREE_BOTH
        else:
            m.personal_questions_match = Match.Agreement.AGREE_1_TO_2
        m.save()
    else:
        match = Match.objects.filter(user2=request.user, user1=comrade)
        if len(match) > 1:
            return HttpResponseNotFound(
                '<h1>Error. There are 2 same matches in the database. Contact the administration. </h1>')
        if match:
            m = match[0]
            if m.personal_questions_match == Match.Agreement.AGREE_1_TO_2:
                m.personal_questions_match = Match.Agreement.AGREE_BOTH
            else:
                m.personal_questions_match = Match.Agreement.AGREE_2_TO_1
            m.save()
        else:
            return HttpResponseNotFound('<h1>Error. There are 2 same matches in the database. Contact the administration. </h1>')

    questions_delete(request.user, comrade)
    return redirect("view_answers")

##################################
# Elements used for the home page
##################################

# Auxiliary


def select_comrade_for_me(suspect):
    available_users = []
    try:
        suspect_data = UserData.objects.get(user=suspect)
    except User.DoesNotExist:
        return suspect
    if (suspect_data.searching_for == 'Both'):
        users_data = UserData.objects.filter(Q(searching_for=suspect_data.sex) or Q(searching_for='Both')).all()
    else:
        users_data = UserData.objects.filter(Q(sex=suspect_data.searching_for),(Q(searching_for=suspect_data.sex) | Q(searching_for='Both'))).all()
    for u in users_data:
        match = Match.objects.filter(
            Q(
                Q(user1=suspect, user2=u.user),
                ~Q(chatting_match=Match.Agreement.AGREE_2_TO_1)
            ) |
            Q(
                Q(user1=u.user, user2=suspect),
                ~Q(chatting_match=Match.Agreement.AGREE_1_TO_2)
            )
        )
        if not match:
            if u.personality and have_i_question(u):  # if u has personality and at least 1 question
                available_users.append(u.user)
    if len(available_users) == 0:
        return suspect
    else:
        return choose_best_by_personality(suspect.profile.personality, available_users)


def create_match(us1, us2):  # first requested, then friend
    if us1.username < us2.username:
        match = Match.objects.create(user1=us1, user2=us2, chatting_match=Match.Agreement.AGREE_1_TO_2)
    else:
        match = Match.objects.create(user2=us1, user1=us2, chatting_match=Match.Agreement.AGREE_2_TO_1)
    match.save()


# Main

@login_required
def view_people(request):
    age = description = location = candidate = userid = photo = ''
    user = request.user
    chats = UserChat.chats_info(user)
    my_data = UserData.objects.get(user=request.user)
    personality_error = False
    if not my_data.personality or not have_i_question(my_data):  # if u has personality and at least 1 question
        display = False
    else:
        candidate = select_comrade_for_me(request.user)
        userid = candidate.id
        if request.user == candidate:
            display = False
        else:
            display = True
            candidate_info = UserData.objects.filter(user=candidate)

            for u in candidate_info:
                description = u.description
                if u.photo:
                    photo = u.photo
                else:
                    photo = "/images/user_profile_pictures/default.jpg/"
                age = calculate_age(u.birth)
                location = float("{0:.2f}".format(distance_between(candidate, request.user)))
    return render(request, 'html_pages/view_people.html',
                  {"personerror": personality_error, 'chats': chats, 'username': user.username, "desc": description,
                   "age": age, "loc": location,
                   "nick": candidate, "name": userid, "photo": photo,
                   "display": display, 'media_url': settings.STATIC_URL})


def yes_crush(request, user_id=None):
    comrade = User.objects.get(id=str(user_id))
    "statistics"
    log_com = UserLog.objects.get(user=comrade)
    log_my = UserLog.objects.get(user=request.user)
    log_com.likes_receive += 1
    log_my.likes_sent += 1
    log_my.rating = log_com.likes_receive - log_my.likes_sent
    log_com.save()
    log_my.save()
    "end of statistics"

    match = Match.objects.filter(user1=request.user, user2=comrade)
    if match:
        if len(match) > 1:
            return HttpResponseNotFound(
                '<h1>Error. There are 2 same matches in the database. Contact the administration. </h1>')
        m = match[0]
        if m.chatting_match == Match.Agreement.AGREE_2_TO_1:
            m.chatting_match = Match.Agreement.AGREE_BOTH
        else:
            m.chatting_match = Match.Agreement.AGREE_1_TO_2
        m.save()
    else:
        match = Match.objects.filter(user2=request.user, user1=comrade)
        if len(match) > 1:
            return HttpResponseNotFound(
                '<h1>Error. There are 2 same matches in the database. Contact the administration. </h1>')
        if match:
            m = match[0]
            if m.chatting_match == Match.Agreement.AGREE_1_TO_2:
                m.chatting_match = Match.Agreement.AGREE_BOTH
            else:
                m.chatting_match = Match.Agreement.AGREE_2_TO_1
            m.save()
        else:
            create_match(request.user, comrade)

    return redirect("view_people")


def no_crush(request, user_id=None):
    match_decline(request.user, user_id)
    return redirect("view_people")


# Statistics

@receiver(user_logged_in)
def iterate_logins(request, *args, **kwargs):
    try:
        log = UserLog.objects.get(user=request.user)
        log.logins += 1
        log.save()
    except User.DoesNotExist:
        log = UserLog(user=request.user)
        log.save()


# Location

@receiver(user_logged_in)
def update_geolocation(sender, user, request, *args, **kwargs):
    try:
        usr = UserData.objects.get(user=user)
    except UserData.DoesNotExist:
        print("\nError, clear the database of users and register them again. \n")
        return
    ip = get_client_ip(request)
    x = urllib.request.urlopen('http://ip-api.com/json/' + ip + '?fields=lat,lon')
    data = x.read()
    js = json.loads(data.decode('utf-8'))
    try:
        usr.latitude = js['lat']
        usr.longitude = js['lon']
        usr.save()
    except KeyError:
        usr.latitude = 0
        usr.longitude = 0
        usr.save()


"end of localization"


@login_required
@require_http_methods(["GET", "POST"])
def add_personal_questions(request):
    if PersonalQuestionUser.objects.filter(user=request.user):
        return redirect('/')
    else:
        formset_form = formset_factory(PersonalQuestionsCreateForm, extra=5)
        if request.method == 'POST':
            formset = formset_form(request.POST)
            if formset.is_valid():
                for i, form in enumerate(formset):
                    if form.is_valid():
                        question = form.save()
                        # question.refresh_from_db()
                        # question.content = form.get.cleaned_data("content")
                        question_user = PersonalQuestionUser(questionID=question, user=request.user)
                        question_user.save()
                return redirect('/')
        else:
            formset = formset_form()
        return render(request, 'html_pages/add_personal_questions.html', {'formset': formset})


@require_http_methods(["GET", "POST"])
def remind_pass(request):
    # if this is a POST request we need to process the form data
    if request.method == 'POST':
        # create a form instance and populate it with data from the request:
        form = RemainForm(request.POST)
        # check whether it's valid:
        if form.is_valid():
            # process the data in form.cleaned_data as required
            message = form.cleaned_data['message']
            try:
                user = User.objects.get(username=str(message))
                new_password = generate_pass(8)
                user.set_password(new_password)
                user.save()
                send_email(str(user.email), str(new_password))
                return redirect('/')
            except User.DoesNotExist:
                return redirect('/')

    # if a GET (or any other method) we'll create a blank forms
    else:
        form = RemainForm()

    return render(request, 'registration/remain_pass.html', {'formset': form})
