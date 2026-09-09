"""
Regression tests for MenuHelper's as_table() -> menu mapping.

The fork's user-authentication menu crashed with
``ValueError: zip() argument 2 is shorter than argument 1`` as soon as any
user row was displayed: as_table() terminates the last data row with a
newline, so a naive split() produced an empty trailing row which the strict
zip (enabled in the Ruff zip-with-explicit-strict pass) rejected.
"""

from archinstall.lib.menu.menu_helper import MenuHelper
from archinstall.lib.models.users import Password, User


def test_table_to_data_mapping_single_user() -> None:
	users = [User('cal', Password(plaintext='sup3rSecret!'), sudo=True)]

	mapping = MenuHelper(users)._table_to_data_mapping(users)

	# two header rows + one data row, no trailing empty row
	values = list(mapping.values())
	assert len(values) == 3
	assert values[:2] == [None, None]
	assert values[2] is users[0]


def test_table_to_data_mapping_multiple_users() -> None:
	users = [
		User('cal', Password(plaintext='sup3rSecret!'), sudo=True),
		User('root', Password(plaintext='sup3rSecret!'), sudo=False),
	]

	mapping = MenuHelper(users)._table_to_data_mapping(users)

	values = list(mapping.values())
	assert len(values) == 4
	assert values[:2] == [None, None]
	assert values[2] is users[0]
	assert values[3] is users[1]


def test_table_to_data_mapping_no_data_yields_no_rows() -> None:
	mapping = MenuHelper([])._table_to_data_mapping([])

	assert mapping == {}
