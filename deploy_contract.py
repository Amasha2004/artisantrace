import json
from web3 import Web3
from solcx import compile_source, install_solc

# Install Solidity compiler
install_solc('0.8.0')

# Connect to Ganache
w3 = Web3(Web3.HTTPProvider('http://127.0.0.1:8545'))
print(f'Connected to Ganache: {w3.is_connected()}')

# Read contract source
with open('contract.sol', 'r') as f:
    source = f.read()

# Compile contract
compiled = compile_source(source, output_values=['abi', 'bin'],
                          solc_version='0.8.0')
contract_id = list(compiled.keys())[0]
abi = compiled[contract_id]['abi']
bytecode = compiled[contract_id]['bin']

# Deploy contract using first Ganache account
account = w3.eth.accounts[0]
Contract = w3.eth.contract(abi=abi, bytecode=bytecode)
tx_hash = Contract.constructor().transact({'from': account})
tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

contract_address = tx_receipt.contractAddress
print(f'Contract deployed at: {contract_address}')

# Save ABI and address to file — Flask will read this
with open('contract_info.json', 'w') as f:
    json.dump({'address': contract_address, 'abi': abi}, f, indent=2)

print('contract_info.json saved successfully!')