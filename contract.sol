// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract ArtisanTrace {

    struct Product {
        string product_code;
        string name;
        string category;
        string artisan_name;
        string origin;
        uint256 filed_at;
        bool exists;
    }

    mapping(string => Product) private products;
    string[] public productCodes;
    address public owner;

    event ProductFiled(
        string product_code,
        string name,
        string artisan_name,
        uint256 filed_at
    );

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Not authorized");
        _;
    }

    function fileProduct(
        string memory _code,
        string memory _name,
        string memory _category,
        string memory _artisan,
        string memory _origin
    ) public onlyOwner {
        require(!products[_code].exists, "Product already filed");

        products[_code] = Product({
            product_code: _code,
            name:         _name,
            category:     _category,
            artisan_name: _artisan,
            origin:       _origin,
            filed_at:     block.timestamp,
            exists:       true
        });

        productCodes.push(_code);
        emit ProductFiled(_code, _name, _artisan, block.timestamp);
    }

    function getProduct(string memory _code) public view
        returns (string memory, string memory, string memory, string memory, string memory, uint256)
    {
        require(products[_code].exists, "Product not found");
        Product memory p = products[_code];
        return (p.product_code, p.name, p.category, p.artisan_name, p.origin, p.filed_at);
    }

    function getTotalProducts() public view returns (uint256) {
        return productCodes.length;
    }

    function productExists(string memory _code) public view returns (bool) {
        return products[_code].exists;
    }
}