from trytond.pool import Pool, PoolMeta



class Account(metaclass=PoolMeta):
    __name__ = 'account.account'

    @classmethod
    def delete_account_type(cls, accounts):
        pool = Pool()
        Account = pool.get('account.account')
        parents = []
        for account in accounts:
            if account.code and len(account.code) > 6 and account.type:
                if account.parent and account.parent not in parents:
                    parents.append(account.parent)
        print(parents)
        for parent in parents:
            if parent.type:
                print('parent delete:', parent)
                Account.write([parent], {'type': None})