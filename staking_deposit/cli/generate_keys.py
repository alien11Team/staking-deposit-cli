import os
import click
import yaml
from typing import (
    Any,
    Callable,
)

from eth_typing import HexAddress
from staking_deposit.credentials import (
    CredentialList,
)
from staking_deposit.exceptions import ValidationError
from staking_deposit.utils.validation import (
    verify_deposit_data_json,
    validate_int_range,
    validate_password_strength,
    validate_eth1_withdrawal_address,
)
from staking_deposit.utils.constants import (
    MAX_DEPOSIT_AMOUNT,
    DEFAULT_VALIDATOR_KEYS_FOLDER_NAME,
)
from staking_deposit.utils.ascii_art import RHINO_0
from staking_deposit.utils.click import (
    captive_prompt_callback,
    choice_prompt_func,
    jit_option,
)
from staking_deposit.utils.intl import (
    closest_match,
    load_text,
)
from staking_deposit.settings import (
    ALL_CHAINS,
    MAINNET,
    PRATER,
    get_chain_setting,
    get_devnet_chain_setting,
)


def get_password(text: str) -> str:
    return click.prompt(text, hide_input=True, show_default=False, type=str)


def generate_keys_arguments_decorator(function: Callable[..., Any]) -> Callable[..., Any]:
    '''
    This is a decorator that, when applied to a parent-command, implements the
    to obtain the necessary arguments for the generate_keys() subcommand.
    '''
    decorators = [
        jit_option(
            # Only for devnet tests
            default=None,
            param_decls='--devnet_chain_setting',
        ),
        jit_option(
            callback=captive_prompt_callback(
                lambda num: validate_int_range(num, 1, 2**32),
                lambda: load_text(['num_validators', 'prompt'], func='generate_keys_arguments_decorator')
            ),
            default=1,
            help=lambda: load_text(['num_validators', 'help'], func='generate_keys_arguments_decorator'),
            param_decls="--num_validators",
            #prompt=lambda: load_text(['num_validators', 'prompt'], func='generate_keys_arguments_decorator'),
        ),
        jit_option(
            help=lambda: load_text(['folder', 'help'], func='generate_keys_arguments_decorator'),
            param_decls='--folder',
            default="/basicconfig",
            type=click.Path(exists=True, file_okay=False, dir_okay=True),
        ),
        jit_option(
            callback=captive_prompt_callback(
                lambda x: closest_match(x, list(ALL_CHAINS.keys())),
                choice_prompt_func(
                    lambda: load_text(['chain', 'prompt'], func='generate_keys_arguments_decorator'),
                    list(ALL_CHAINS.keys())
                ),
            ),
            default=MAINNET,
            help=lambda: load_text(['chain', 'help'], func='generate_keys_arguments_decorator'),
            param_decls='--chain',
            # prompt=choice_prompt_func(
            #     lambda: load_text(['chain', 'prompt'], func='generate_keys_arguments_decorator'),
            #     # Since `prater` is alias of `goerli`, do not show `prater` in the prompt message.
            #     list(key for key in ALL_CHAINS.keys() if key != PRATER)
            # ),
        ),
        jit_option(
            # callback=captive_prompt_callback(
            #     validate_password_strength,
            #     lambda:load_text(['keystore_password', 'prompt'], func='generate_keys_arguments_decorator'),
            #     lambda:load_text(['keystore_password', 'confirm'], func='generate_keys_arguments_decorator'),
            #     lambda: load_text(['keystore_password', 'mismatch'], func='generate_keys_arguments_decorator'),
            #     True,
            # ),
            default="12345678",
            help=lambda: load_text(['keystore_password', 'help'], func='generate_keys_arguments_decorator'),
            hide_input=True,
            param_decls='--keystore_password',
            #prompt=lambda: load_text(['keystore_password', 'prompt'], func='generate_keys_arguments_decorator'),
        ),
        jit_option(
            callback=captive_prompt_callback(
                lambda address: validate_eth1_withdrawal_address(None, None, address),
                lambda: load_text(['arg_execution_address', 'prompt'], func='generate_keys_arguments_decorator'),
                lambda: load_text(['arg_execution_address', 'confirm'], func='generate_keys_arguments_decorator'),
                lambda: load_text(['arg_execution_address', 'mismatch'], func='generate_keys_arguments_decorator'),
            ),
            default=None,
            help=lambda: load_text(['arg_execution_address', 'help'], func='generate_keys_arguments_decorator'),
            param_decls=['--execution_address', '--eth1_withdrawal_address'],
        ),
    ]
    for decorator in reversed(decorators):
        function = decorator(function)
    return function


@click.command()
@click.pass_context
def generate_keys(ctx: click.Context, validator_start_index: int,
                  num_validators: int, folder: str, chain: str, keystore_password: str,
                  execution_address: HexAddress, devnet_chain_setting: str, **kwargs: Any) -> None:
    mnemonic = ctx.obj['mnemonic']
    mnemonic_password = ctx.obj['mnemonic_password']
    global MAX_DEPOSIT_AMOUNT
    amounts = [MAX_DEPOSIT_AMOUNT] * num_validators
    folder = os.path.join(folder, DEFAULT_VALIDATOR_KEYS_FOLDER_NAME)
    chain_setting = get_chain_setting(chain)
    if devnet_chain_setting is not None:
        click.echo('\n%s\n' % '**[Warning] Using devnet chain setting to generate the SignedBLSToExecutionChange.**\t')
        # devnet_chain_setting_dict = json.loads(devnet_chain_setting)
        # 读取 YAML 文件
        with open(devnet_chain_setting, 'r') as file:
            devnet_chain_setting_dict = yaml.load(file, Loader=yaml.BaseLoader)

            print("6666")
        chain_setting = get_devnet_chain_setting(
            network_name=devnet_chain_setting_dict.get('CHAIN_ID', "mainnet"),
            genesis_fork_version=devnet_chain_setting_dict['GENESIS_FORK_VERSION'],
            genesis_validator_root=devnet_chain_setting_dict['GENESIS_VALIDATOR_ROOT']
        )
        MAX_DEPOSIT_AMOUNT = int(devnet_chain_setting_dict['MAX_EFFECTIVE_BALANCE'])
        amounts = [MAX_DEPOSIT_AMOUNT] * num_validators
    if not os.path.exists(folder):
        os.mkdir(folder)
    click.clear()
    click.echo(RHINO_0)
    click.echo(load_text(['msg_key_creation']))
    credentials = CredentialList.from_mnemonic(
        mnemonic=mnemonic,
        mnemonic_password=mnemonic_password,
        num_keys=num_validators,
        amounts=amounts,
        chain_setting=chain_setting,
        start_index=validator_start_index,
        hex_eth1_withdrawal_address=execution_address,
    )
    keystore_filefolders = credentials.export_keystores(password=keystore_password, folder=folder)
    deposits_file = credentials.export_deposit_data_json(folder=folder)
    if not credentials.verify_keystores(keystore_filefolders=keystore_filefolders, password=keystore_password):
        raise ValidationError(load_text(['err_verify_keystores']))
    if not verify_deposit_data_json(deposits_file, credentials.credentials):
        raise ValidationError(load_text(['err_verify_deposit']))
    click.echo(load_text(['msg_creation_success']) + folder)
    # click.pause(load_text(['msg_pause']))
