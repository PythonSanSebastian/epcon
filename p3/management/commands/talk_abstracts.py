# -*- coding: utf-8 -*-
"""
Print out a JSON of accepted talks with the abstracts, schedule and speaker tickets status.
"""
from   django.core.management.base import BaseCommand, CommandError
from   conference   import models

from   p3           import models as p3_models
from   assopy       import models as assopy_models

from   collections  import OrderedDict
from   optparse     import make_option
import simplejson   as json
import traceback

### Globals
VERBOSE = False


### Helpers
def speaker_listing(talk):
    return u', '.join(
        u'{} {}'.format(speaker.user.first_name, speaker.user.last_name)
        for speaker in talk.get_all_speakers())


def speaker_emails(talk):
    return u', '.join(
        u'{}'.format(speaker.user.email) for speaker in talk.get_all_speakers())


def speaker_twitters(talk):
    return u', '.join(
        u'@{}'.format(speaker.user.attendeeprofile.p3_profile.twitter)
        for speaker in talk.get_all_speakers())


def get_orders_from(user):
    return assopy_models.Order.objects.filter(_complete=True, user=user.id)


def get_tickets_assigned_to(user):
    return p3_models.TicketConference.objects.filter(assigned_to=user.email)


def is_ticket_assigned_to_someone_else(ticket, user):
    tickets = p3_models.TicketConference.objects.filter(ticket_id=ticket.id)

    if not tickets:
        return False

    if len(tickets) > 1:
        raise RuntimeError('You got more than one ticket from a ticket_id.'
                           'Tickets obtained: {}.'.format(tickets))

    tkt = tickets[0]
    if tkt.ticket.user_id != user.id:
        return True

    if not tkt.assigned_to:
        return False

    if tkt.assigned_to == user.email:
        return False
    else:
        return True


def has_ticket(user):
    tickets = get_tickets_assigned_to(user)
    if tickets:
        return True

    user_tickets = list(user.ticket_set.all())
    orders = get_orders_from(user)
    if orders:
        order_tkts = [ordi.ticket
                      for order in orders
                      for ordi in order.orderitem_set.all()
                      if ordi.ticket is not None]
        user_tickets.extend(order_tkts)

    for tkt in user_tickets:
        if tkt.fare.code.startswith('T'):
            if not is_ticket_assigned_to_someone_else(tkt, user):
                return True

    return False


def have_tickets(talk):
    usrs = talk.get_all_speakers()
    have_tkt = []
    for user in usrs:
        try:
            have_tkt.append(has_ticket(user.user))
        except:
            print(traceback.format_exc())
            raise

    return have_tkt


def clean_title(title):
    title = title.strip()
    if not title:
        return title

    # Remove whitespace
    title = title.strip()
    # Remove double spaces
    title = title.replace("  ", " ")
    # Remove quotes
    if title[0] == '"' and title[-1] == '"':
        title = title[1:-1]
    return title


def talk_track_title(talk):
    event = talk.get_event()
    if not event:
        return ''
    return ', '.join([tr.title for tr in event.tracks.all()])


def talk_schedule(talk):
    event = talk.get_event()
    if not event:
        if VERBOSE:
            print('ERROR: Talk {} is not scheduled.'.format(talk))
        return ''
    timerange = event.get_time_range()
    return '{}, {}'.format(str(timerange[0]), str(timerange[1]))


def talk_votes(talk):
    qs = models.VotoTalk.objects.filter(talk=talk.id).all()
    user_votes = []
    for v in qs:
        user_votes.append({v.user_id: v.vote})
    return user_votes


def speaker_companies(talk):
    companies = sorted(
        set(speaker.user.attendeeprofile.company
            for speaker in talk.speakers.all()
                if speaker.user.attendeeprofile))
    return u', '.join(companies)


class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option('--verbose',
             action='store_true',
             dest='verbose',
             help='Will output some warning while running.',
        ),
        make_option('--talk_status',
             action='store',
             dest='talk_status',
             default='proposed',
             choices=['accepted', 'proposed', 'canceled'],
             help='The status of the talks to be put in the report. '
                  'Choices: accepted, proposed, canceled',
        ),
        make_option('--votes',
             action='store_true',
             dest='votes',
             default=False,
             help='Add the votes to each talk.',
        ),

        # make_option('--option',
        #     action='store',
        #     dest='option_attr',
        #     default=0,
        #     type='int',
        #     help='Help text',
        # ),
    )

    def handle(self, *args, **options):
        try:
            conference = args[0]
        except IndexError:
            raise CommandError('conference not specified')

        if options['verbose']:
            VERBOSE = True

        # Group by admin types
        talks = OrderedDict()
        for adm_type, type_name in dict(models.TALK_ADMIN_TYPE).items():
            talks[type_name] = list(models.Talk.objects
                                    .filter(conference=conference,
                                            status=options['talk_status'],
                                            admin_type=adm_type))

        type_groups = {'talk':        ['t_30', 't_45', 't_60'],
                       'interactive': ['i_60'],
                       'training':    ['r_180'],
                       'panel':       ['p_60', 'p_90'],
                       'poster':      ['p_180'],
                       'helpdesk':    ['h_180'],
                      }

        for grp_name, grp_types in type_groups.items():
            grp_talks = []
            for talk_type in grp_types:
                bag = list(models.Talk.objects
                           .filter(conference=conference,
                                   status=options['talk_status'],
                                   type=talk_type,
                                   admin_type=''))
                grp_talks.extend(bag)

            talks[grp_name] = grp_talks

        sessions = OrderedDict()
        # Print list of submissions
        for type_name, session_talks in talks.items():
            if not session_talks:
                continue

            sessions[type_name] = OrderedDict()

            # Sort by talk title using title case
            session_talks.sort(key=lambda talk: clean_title(talk.title).encode('utf-8').title())
            for talk in session_talks:

                sessions[type_name][talk.id] = {
                'id':             talk.id,
                'admin_type':     talk.get_admin_type_display().encode('utf-8'),
                'type':           talk.get_type_display().encode('utf-8'),
                'duration':       talk.duration,
                'level':          talk.get_level_display().encode('utf-8'),
                'track_title':    talk_track_title(talk).encode('utf-8'),
                'timerange':      talk_schedule(talk).encode('utf-8'),
                'tags':           [str(t) for t in talk.tags.all()],
                'url':            'https://{}.europython.eu/{}'.format(conference, talk.get_absolute_url()).encode('utf-8'),
                'tag_categories': [tag.category.encode('utf-8') for tag in talk.tags.all()],
                'sub_community':  talk.p3_talk.sub_community.encode('utf-8'),
                'title':          clean_title(talk.title).encode('utf-8'),
                'sub_title':      clean_title(talk.sub_title).encode('utf-8'),
                'status':         talk.status.encode('utf-8'),
                'language':       talk.get_language_display().encode('utf-8'),
                'have_tickets':   have_tickets(talk),
                'abstract_long':  [abst.body.encode('utf-8') for abst in talk.abstracts.all()],
                'abstract_short': talk.abstract_short.encode('utf-8'),
                'abstract_extra': talk.abstract_extra.encode('utf-8'),
                'speakers':       speaker_listing(talk).encode('utf-8'),
                'companies':      speaker_companies(talk).encode('utf-8'),
                'emails':         speaker_emails(talk).encode('utf-8'),
                'twitters':       speaker_twitters(talk).encode('utf-8'),
                }

                if options['votes']:
                    sessions[type_name][talk.id]['user_votes'] = talk_votes(talk)

        print(json.dumps(sessions, indent=2))
