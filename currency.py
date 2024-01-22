"""CURRENCY MODULE"""
from datetime import date
from trytond.pool import PoolMeta, Pool
import requests


class Cron(metaclass=PoolMeta):
    "Currency Cron"
    __name__ = 'currency.cron'

    @classmethod
    def __setup__(cls):
        # pylint: disable=no-member
        super(Cron, cls).__setup__()

        cls.source.selection.append(('bdc', 'Banco de datos de Colombia'))
        cls._buttons.update({
            'run': {},
        })

    @classmethod
    def update(cls, crons=None):
        """Function that update currency selected"""
        # pylint: disable=no-member

        pool = Pool()
        rate = pool.get('currency.currency.rate')
        today_date = date.today()

        if crons is None:
            crons = cls.search([])

        if not crons:
            pass
            # raise UserError("TASA DE CAMBIO INVALIDA",
            #                 "No fue posible encontrar una tasa de cambio registrada")
        else:
            currency_rates = []
            for cron in crons:
                if cron.source == "bdc":
                    dollar_price = cls.get_price_dollar_bdc()
                    dollar_rate = 1 / dollar_price
                    currency_id = cron.currency
                    currency_symbol = cron.currency.symbol

                    if currency_symbol == "US$":
                        currency_rates = rate.search(
                            ["currency", "=", currency_id])

                        if currency_rates:
                            currency_rates[0].rate = dollar_rate
                            currency_rates[0].date = today_date
                        else:
                            currency_rate = rate(currency=currency_id,
                                                 rate=dollar_rate,
                                                 date=today_date)
                            currency_rates.append(currency_rate)
                else:
                    currency_rates.extend(cron._update())

            rate.save(currency_rates)
            cls.save(crons)

    @classmethod
    def get_price_dollar_bdc(cls):
        """Function that get info from api_rest url"""

        api_url = "https://www.datos.gov.co/resource/32sa-8pi3.json"
        response = requests.get(api_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            price_dollar = data[0]["valor"]
        return price_dollar
