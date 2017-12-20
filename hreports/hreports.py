# -*- coding: utf-8 -*-

"""Main module."""

import os
import io
import subprocess
import datetime
import tempfile
from jinja2 import Environment, ChoiceLoader, \
    FileSystemLoader, PackageLoader, select_autoescape
from .template_filters import datetimeformat, german_float, \
    last_day_of_month


class Hreport(object):
    def __init__(self, config):
        self.config = config

        cfg_path = os.path.dirname(self.config.cfg_file)
        self.cfg_templates = os.path.join(cfg_path, 'templates')

        loader = ChoiceLoader([
                    FileSystemLoader('./'),
                    FileSystemLoader('/templates'),
                    FileSystemLoader(self.cfg_templates),
                    PackageLoader('hreports', 'templates'),
        ])
        self.env = Environment(loader=loader,
                               autoescape=select_autoescape(['html', 'xml'])
                               )

        self.env.filters['datetime'] = datetimeformat
        self.env.filters['german_float'] = german_float
        self.env.filters['last_day_of_month'] = last_day_of_month

    def get_global_config(self):
        return self.config.data.get('global', None)

    def get_report_config(self, name):
        return self.config.data.get('reports').get(name, None)

    def get_report_config_value(self, name, key):
        report_config = self.config.data.get('reports').get(name, None)
        if report_config:
            value = report_config.get(key, None)
        else:
            value = False
        if not value:
            # Try global section
            return self.get_global_config_value(value)
        return value

    def get_global_config_value(self, key):
        return self.config.data.get('global').get(key, None)

    def run(self, name=False, query=False, ledger=False):
        if name:
            query = self.get_report_config_value(name, 'query')
            ledger = self.get_report_config_value(name, 'ledger')

        if not ledger:
            ledger = self.get_global_config_value('ledger')

        query = self.env.from_string(query)
        query = query.render(self.get_context(name))

        if ledger:
            cmd = 'hledger -f %s %s' % (ledger, query)
        else:
            cmd = 'hledger %s' % query
        self.config.cmd = cmd
        return unicode(subprocess.check_output(cmd.split(' ')), 'utf-8')

    def render_strings_in_dict(self, data_dict, context, section=False):
        if not data_dict:
            return context
        for key, value in data_dict.items():
            if isinstance(value, str):
                value_template = self.env.from_string(value)
                data_dict[key] = value_template.render(context)
        if section:
            context.update({section: data_dict})
        else:
            context.update(data_dict)
        return context

    def get_context(self, name=False):
        """Build context data for the template.

        The template context dict is evaluated in this order:

            1. Builtins at {}
            2. variables of the global section at {}
            3. global section at {'global'}
            4. variables of the report section {'report'}
            5 report section at {}
        """
        context = {}

        builtins = {'now': datetime.datetime.now()}
        context.update(builtins)

        global_config = self.get_global_config()
        if 'variables' in global_config:
            global_variables = global_config.get('variables', {})
            context = self.render_strings_in_dict(global_variables,
                                                  context)
        self.render_strings_in_dict(global_config, context, 'global')

        report_config = self.get_report_config(name)
        if report_config:
            report_variables = report_config.get('variables', {})
            self.render_strings_in_dict(report_variables, context)

        self.render_strings_in_dict(report_config, context, 'report')

        context.update({'hreport': self})

        return context

    def render(self, name):

        template_name = self.get_report_config_value(name, 'template')

        if not template_name:
            return self.run(name)

        template = self.env.get_template(template_name)
        context = self.get_context(name)
        context['output'] = self.run(name).splitlines()
        return template.render(context)

    def save(self, name):
        input_file = tempfile.NamedTemporaryFile(dir='.',
                                                 delete=False)
        input_file.close()

        with io.open(input_file.name, 'w',
                     encoding='utf-8') as input_file:
            input_file.write(self.render(name))
        output_file = self.get_report_config_value(name, 'filename')

        if not output_file:
            output_file = '%s.pdf' % name

        output_file_template = self.env.from_string(output_file)
        context = self.get_context(name)
        output_file = output_file_template.render(context)

        cmd = 'pandoc %s -t html5 -o %s' % (input_file.name,
                                            output_file)

        styling = self.get_report_config_value(name, 'styling')
        template_name = self.get_report_config_value(name,
                                                     'template')
        if styling:
            styling = os.path.join(self.cfg_templates, styling)
            styling = '--css "%s"' % styling
        elif template_name:
            styling_default = template_name.split('.')[0] + '.css'
            styling_default_path = os.path.join(self.cfg_templates,
                                                styling_default)
            if os.path.exists(styling_default_path):
                cmd = cmd + ' --css %s' % styling_default_path
        input_file.close()
        unicode(subprocess.check_output(cmd.split(' ')), 'utf-8')
        os.unlink(input_file.name)
        return output_file
