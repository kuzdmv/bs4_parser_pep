import re
import logging

import requests_cache
from bs4 import BeautifulSoup
from tqdm import tqdm
from urllib.parse import urljoin

from constants import BASE_DIR, MAIN_DOC_URL, PEP_URL, EXPECTED_STATUS
from configs import configure_argument_parser, configure_logging
from outputs import control_output
from utils import get_response, find_tag


def whats_new(session):
    whats_new_url = urljoin(MAIN_DOC_URL, 'whatsnew/')
    response = get_response(session, whats_new_url)
    if response is None:
        return
    soup = BeautifulSoup(response.text, features='lxml')
    main_div = find_tag(soup, 'section', attrs={'id': 'what-s-new-in-python'})
    div_with_ul = find_tag(main_div, 'div', attrs={'class': 'toctree-wrapper'})
    sections_by_python = div_with_ul.find_all(
        'li', attrs={'class': 'toctree-l1'}
    )
    results = [('Ссылка на статью', 'Заголовок', 'Редактор, Автор')]
    for section in tqdm(sections_by_python):
        version_a_tag = section.find('a')
        href = version_a_tag['href']
        version_link = urljoin(whats_new_url, href)
        response1 = get_response(session, version_link)
        if response1 is None:
            continue
        soup = BeautifulSoup(response1.text, features='lxml')
        h1 = find_tag(soup, 'h1')
        dl = soup.find('dl')
        dl_text = dl.text.replace('\n', ' ')
        results.append((version_link, h1.text, dl_text))
    return results


def latest_versions(session):
    response = get_response(session, MAIN_DOC_URL)
    if response is None:
        return
    soup = BeautifulSoup(response.text, features='lxml')
    sidebar = soup.find('div', {'class': 'sphinxsidebarwrapper'})
    ul_tags = sidebar.find_all('ul')
    results = []
    for ul in ul_tags:
        if 'All versions' in ul.text:
            a_tags = ul.find_all('a')
            break
        else:
            raise Exception('Ничего не нашлось')
    results = [('Ссылка на документацию', 'Версия', 'Статус')]
    pattern = r'Python (?P<version>\d\.\d+) \((?P<status>.*)\)'
    for a_tag in a_tags:
        link = a_tag['href']
        text_match = re.search(pattern, a_tag.text)
        if text_match is not None:
            version, status = text_match.groups()
        else:
            version, status = a_tag.text, ''
        results.append(
            (link, version, status)
        )
    return results


def download(session):
    downloads_url = urljoin(MAIN_DOC_URL, 'download.html')
    response = session.get(downloads_url)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, features='lxml')
    main_tag = soup.find('div', {'role': 'main'})
    table_tag = main_tag.find('table', {'class': 'docutils'})
    pdf_a4_tag = table_tag.find('a', {'href': re.compile(r'.+pdf-a4\.zip$')})
    pdf_a4_link = pdf_a4_tag['href']
    archive_url = urljoin(downloads_url, pdf_a4_link)
    filename = archive_url.split('/')[-1]
    downloads_dir = BASE_DIR / 'downloads'
    downloads_dir.mkdir(exist_ok=True)
    archive_path = downloads_dir / filename
    response = session.get(archive_url)
    with open(archive_path, 'wb') as file:
        file.write(response.content)
    logging.info(f'Архив был загружен и сохранён: {archive_path}')


def pep(session):
    response = get_response(session, PEP_URL)
    if response is None:
        return
    soup = BeautifulSoup(response.text, features='lxml')
    section_tag = find_tag(soup, 'section', attrs={'id': 'index-by-category'})
    table_tags = section_tag.find_all(
        'table', attrs={'class': 'pep-zero-table docutils align-default'}
    )
    results = [('Статус', 'Количество')]
    count_dict = {}
    for table_tag in tqdm(table_tags):
        tbody_tag = find_tag(table_tag, 'tbody')
        tr_tags = tbody_tag.find_all('tr')
        for tr_tag in tr_tags:
            td_tag = tr_tag.find_all('td')
            links = td_tag[2].find('a')
            if links is not None:
                href = links['href']
                link_pep = urljoin(PEP_URL, href)
                pep_status = td_tag[0].text[1:]
                response = get_response(session, link_pep)
                if response is None:
                    continue
                soup = BeautifulSoup(response.text, features='lxml')
                dl_tag = soup.find(
                    'dl', attrs={'class': 'rfc2822 field-list simple'}
                )
                status_tag = dl_tag.find(string='Status')
                status = status_tag.parent.next_sibling.next_sibling.text
                if status not in count_dict:
                    count_dict[status] = 1
                else:
                    count_dict[status] += 1
                if status not in EXPECTED_STATUS[pep_status]:
                    logging.warning(
                        f'''Несовпадают статусы по адресу {link_pep}.
                        Ожидался - {EXPECTED_STATUS[pep_status]}.
                        Получили - {status}.'''
                    )
    total_sum = 0
    for i in count_dict:
        results.append([i, count_dict[i]])
        total_sum += count_dict[i]
    results.append(['Total ', total_sum])
    return results


MODE_TO_FUNCTION = {
    'whats-new': whats_new,
    'latest-versions': latest_versions,
    'download': download,
    'pep': pep,
}


def main():
    configure_logging()
    logging.info('Парсер запущен!')
    arg_parser = configure_argument_parser(MODE_TO_FUNCTION.keys())
    args = arg_parser.parse_args()
    logging.info(f'Аргументы командной строки: {args}')
    session = requests_cache.CachedSession()
    if args.clear_cache:
        session.cache.clear()
    parser_mode = args.mode
    results = MODE_TO_FUNCTION[parser_mode](session)
    if results is not None:
        control_output(results, args)
    logging.info('Парсер завершил работу.')


if __name__ == '__main__':
    main()
