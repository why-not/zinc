
import re
import json
import time
import todoist
from collections import defaultdict
from difflib import SequenceMatcher

def is_project(strg, search=re.compile(r'^[ a-zA-Z_-]*:').search):
    return bool(search(strg))

def is_task(strg, search=re.compile(r'☐|✔').search):
    return bool(search(strg))

def is_done(strg, search=re.compile(r'✔').search):
    return bool(search(strg))

def get_tags(strg):
    return list(map(lambda x: re.sub('@', '', x),
                         re.findall(r'(@\S*)', strg)))

def strip_content(strg):

    # lower case, because that's how I like it.
    # TODO: remove this from the public repo.
    strg = strg.lower().strip()

    # weird specific fix for Todoist specific project.
    if strg == 'inbox:':
        strg = 'Inbox:'

    strg = re.sub(r'\(\d\d\-\d\d\-\d\d\ \d\d:\d\d\)', '', strg) # strip dates.
    strg = re.sub(r'☐|✔|\.', '', strg).strip()
    strg = re.sub(r'(@\S*)', '', strg)
    return strg.strip()

def get_space(strg):
    return re.findall(r'(^\s*)', strg)[0]

def is_blank(strg, search=re.compile(r'^[^A-Za-z]*$').search):
    return bool(search(strg))

def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()


def parse_file(todo_file):
    todo = open(todo_file, 'r')
    todo = todo.readlines()

    items        = []
    projects     = []
    labels       = []
    curr_project = None
    curr_level   = 0
    indent_list  = []
    content_list = [[], [], [], [], []]

    for num, line in enumerate(todo):
        if is_blank(line):
            continue
        item = {}
        item['content'] = strip_content(line)
        # item['content'] = strip_date(item['content'])
        curr_level   = 0

        if is_project(line):
            item['content'] = item['content'].replace(':', '')
            projects.append(item['content'])
            curr_project = item['content']
        else:
            is_task(line) # this is more of an assert statement.
            if is_done(line):
                item['checked'] = 1
            else:
                item['checked'] = 0

            item['label_texts']     = get_tags(line)
            item['project']         = curr_project
            space                   = get_space(line)
            indent                  = int(len(space)/4)
            indent_list.append(indent)
            content_list[indent].append(item['content'])

            if indent > 1:
                item['parent'] = content_list[indent - 1][-1]
            else:
                item['parent'] = None

            items.append(item)
            labels.extend(item['label_texts'])
    return projects, items, list(set(labels))


def get_id_translations(api):
    projects2id = {}
    items2id    = {}
    labels2id   = {}

    remote_items    = api.items.all()
    remote_projects = api.projects.all()
    remote_labels   = api.labels.all()

    for item in remote_labels:
        labels2id[item['name']] = item['id']

    for item in remote_projects:
        projects2id[item['name']] = item['id']

    for item in remote_items:
        if type(item['content']) == type(''):
            items2id[item['content']] = item['id']

    return projects2id, items2id, labels2id


def register_new_local_projects(local_projects, api):
    remote_projects = api.projects.all()
    new_local_projects = []
    remote_projects_list = list(map(lambda x: x['name'], remote_projects))
    for p in local_projects:
        if p in remote_projects_list:
            continue
        else:
            new_local_projects.append(p)
    for p in new_local_projects:
        print(p)
        api.projects.add(p)
    api.commit()


def register_new_local_labels(local_labels, api):
    remote_labels = api.labels.all()
    new_local_labels = []
    remote_labels_list = list(map(lambda x: x['name'], remote_labels))
    for l in local_labels:
        if l in remote_labels_list:
            continue
        else:
            new_local_labels.append(l)
    for l in new_local_labels:
        print(l)
        api.labels.add(l)
    api.commit()


def translate_ids(local_items, projects2id, labels2id):
    _local_items = []
    for item in local_items:
        item['project_id'] = projects2id[item['project']]
        item['labels'] = list(map(lambda x: labels2id[x], item['label_texts']))
        _local_items.append(item)
    return _local_items

def similar_exists(strg, items2id):
    similar_list = []
    similar_debug = []
    for item in items2id:
        if similar(item, strg) > 0.96:
            similar_list.append(items2id[item])
            similar_debug.append((item, similar(item, strg)))
    if len(similar_list) == 1:
        return similar_list[0]
    elif len(similar_list) > 1:
        message = "more than one similar item found {}"
        raise Exception(message.format(similar_debug))
    else:
        return False


def push_local_items(local_items, api):
    items2id = {}
    remote_items = api.items.all()
    for item in remote_items:
        if type(item['content']) == type(''):
            items2id[item['content']] = item['id']


    counter = 0
    for i, item in enumerate(local_items):
        # print('push local debug')
        # print(item)
        # print(item['label_texts'])
        # print(item['labels'])
        # print('*'*10)
        remote_id = similar_exists(item['content'].lower(), items2id)
        if remote_id:
            counter += 1
            itm = api.items.get_by_id(remote_id)
            itm.update(labels=item['labels'])
            if itm['project_id'] != item['project_id']:
                counter += 1
                itm.move(project_id=item['project_id'])
            # if itm['parent_id'] != item['parent_id']:
            #     counter += 1
            #     itm.move(parent_id=item['parent_id'])
        else:
            counter += 1
            api.items.add(item['content'],
                          project_id=item['project_id'],
                          labels=item['labels'])
        print('{} of {}'.format(i, len(local_items)))
        if counter == 90:
            print("counter for push local: {}".format(counter))
            api.commit()
            api.sync()
            time.sleep(1.5)
    print("counter for push local: {}".format(counter))
    api.commit()
    api.sync()
    time.sleep(1.5)



def update_push_local_items(local_items, api):
    api.sync()
    items2id = {}
    remote_items = api.items.all()
    counter = 0
    for item in remote_items:
        if type(item['content']) == type(''):
            items2id[item['content']] = item['id']
    for item in local_items:
        itm = api.items.get_by_id(items2id[item['content']])
        if item['parent']:
            item['parent_id'] = items2id[item['parent']]
            item['id']        = items2id[item['content']]
            if type(item['parent_id']) == int:
                if type(item['id']) == int:
                    if (itm['parent_id'] != item['parent_id']):
                        counter += 1
                        print(item['content'])
                        itm.move(parent_id=item['parent_id'])
                        api.commit()
                        time.sleep(1.5)
        if item['checked']:
            if itm['checked'] != 1:
                counter += 1
                print(item['content'])
                itm.complete()
                api.commit()
                time.sleep(1.5)
    print("counter status at update push: ", counter)


def make_project_datastructure(local_tasks):
    project_dict = defaultdict(list)
    for task in local_tasks:
        project_dict[task['project']].append(task)
    return project_dict


def do_id_translations_inv(api, id2projects, id2labels):
    trans_remote_items = []
    remote_items  = api.items.all()
    for item in remote_items:
        try:
            print('='*10)
            print(item)
            print('-'*10)
            item['project'] = id2projects[item['project_id']]
            item['label_texts']  = list(map(lambda x: id2labels[x], item['labels']))
            print(item['label_texts'])
            print(list(map(lambda x: id2labels[x], item['labels'])))
            print('-'*10)
            print(item)
            print('='*10)
        except KeyError:
            import ipdb; ipdb.set_trace()
            print("-"*10)
            print(item)
            print(item['project_id'])
            print(item['labels'])
            print("KeyError for item, discarding")
            print("-"*10)
        trans_remote_items.append(item)
    return trans_remote_items


def get_id_translations_inv(api):
    id2projects = {}
    id2items    = {}
    id2labels   = {}

    remote_items    = api.items.all()
    remote_projects = api.projects.all()
    remote_labels   = api.labels.all()

    for item in remote_labels:
        id2labels[item['id']] = item['name']

    for item in remote_projects:
        id2projects[item['id']] = item['name']

    for item in remote_items:
        if type(item['content']) == type(''):
            id2items[item['id']] = item['content']

    return id2projects, id2items, id2labels


def make_project_datastructure_remote(api):
    project_dict = defaultdict(list)
    id2projects, id2items, id2labels = get_id_translations_inv(api)
    trans_remote_items = do_id_translations_inv(api,
                                                    id2projects,
                                                    id2labels)

    for task in trans_remote_items:
        try:
            project_dict[task['project']].append(task)
        except KeyError:
            print('KeyError: ')
            print(task)

    return project_dict


def write_to_task_file(api, todo_sync):
    api.sync()
    project_dict = make_project_datastructure_remote(api)
    todo_sync_file = open(todo_sync, 'w+')
    for project in project_dict:
        todo_sync_file.write('\n')
        todo_sync_file.write('{}:\n'.format(project))
        for task in project_dict[project]:
            if type(task['id']) == int:
                if task['checked']:
                    prepend = '✔'
                    continue
                else:
                    prepend = '☐'

                # label string.

                labels = ' @'.join(task['label_texts'])
                if labels:
                    labels = '@' + labels
                # TODO: mod this to add more than 2 levels.
                if type(task['parent_id']) == int:
                    task['level'] = 2
                else:
                    task['level'] = 1

                todo_sync_file.write((('    '*task['level']
                            + prepend
                            + ' {0} {1}\n').format(task['content'], labels)))
    todo_sync_file.close()


def reset_account(api):
    remote_items = api.items.all()
    counter = 0
    for item in remote_items:
        counter += 1
        print(item['content'])
        try:
            itm = api.items.get_by_id(item['id'])
            itm.delete()
        except:
            print('some exception, who cares!')
        if counter > 90:
            counter = 0
            api.commit()
            time.sleep(2)
    try:
        api.commit()
    except:
        api.sync()
        time.sleep(2)
        api.commit()


def reset_labels(api):
    remote_items = api.items.all()
    counter = 0
    for item in remote_items:
        print(item['content'])
        try:
            itm = api.items.get_by_id(item['id'])
            itm.update(labels = [])
            counter += 1
            # itm.delete()
        except :
            print('some exception, who cares!')
        if counter == 90:
            counter = 0
            print("counter reached 90, comitting...")
            api.sync()
            api.commit()
            time.sleep(2)
    api.sync()
    api.commit()




def main():

    # This is the format of a local task:
    # dummy = {'content': 'mo letter mail',
    #          'project': 'misc',
    #          'is_project': False,
    #          'is_done': False,
    #          'tags': [],
    #          'level': 1}


    #  dummy = {'assigned_by_uid': 208884,
    #           'checked': 0,
    #           'child_order': 1,
    #           'collapsed': 0,
    #           'content': '',
    #           'date_added': '2019-06-03T00:41:01Z',
    #           'date_completed': None,
    #           'day_order': -1,
    #           'due': None,
    #           'id': 3228366577,
    #           'in_history': 0,
    #           'is_deleted': 0,
    #           'labels': [],
    #           'parent_id': None,
    #           'priority': 1,
    #           'project_id': 2211471547,
    #           'responsible_uid': None,
    #           'section_id': None,
    #           'sync_id': None,
    #           'user_id': 208884}
    # ----------------------------------

    import sys; sys.path.append('/Users/senthil/Dropbox/workspace/todoist/')
    # from sync import *

    # ----------------------------------

    todo_sync       = '/Users/senthil/Dropbox/workspace/todo/today_sync.todo'

    # parse the todo file and get local state.
    # items need to have parent if parent is not project.
    todo_file       = '/Users/senthil/Dropbox/workspace/todo/today.todo'
    local_projects, local_items, local_labels = parse_file(todo_file)

    # initiate api and get the remote state.
    # api = todoist.TodoistAPI('67d3f9810517d77d4d6ab71f51d8f4a727132f04')
    api = todoist.TodoistAPI('454bca41613803c3e44527fbd7dc64d555bd5b0e')
    api.sync()

    # send local projects, labels up to register them with remote.
    print(local_projects)
    register_new_local_projects(local_projects, api)
    register_new_local_labels(local_labels, api)

    # get translation dictionaries for local to remote sync
    projects2id, items2id, labels2id = get_id_translations(api)
    local_items = translate_ids(local_items, projects2id, labels2id)

    push_local_items(local_items, api)
    update_push_local_items(local_items, api)
    write_to_task_file(api, todo_sync)


if __name__ == '__main__':

    # api = todoist.TodoistAPI('454bca41613803c3e44527fbd7dc64d555bd5b0e')
    # reset_account(api)

    main()

# TODO
# incorporate notes.
# incorporate @done with date.
# incorporate recurring tasks.
# check to see if line order is maintained.
