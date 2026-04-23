// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/token/ERC721/extensions/ERC721Enumerable.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Strings.sol";

contract RSESeat is ERC721, ERC721Enumerable, Ownable {
    mapping(uint256 => bool) private _revoked;
    uint256 private _nextTokenId = 1;
    string private _baseTokenURI;

    error SeatNonTransferable();

    event SeatMinted(uint256 indexed tokenId, address indexed to);
    event SeatRevoked(uint256 indexed tokenId);
    event SeatUnrevoked(uint256 indexed tokenId);

    constructor(address initialOwner) ERC721("RSE Seat", "RSESEAT") Ownable(initialOwner) {}

    function mint(address to) external onlyOwner returns (uint256) {
        uint256 tokenId = _nextTokenId++;
        _safeMint(to, tokenId);
        emit SeatMinted(tokenId, to);
        return tokenId;
    }

    function mintBatch(address[] calldata recipients) external onlyOwner {
        for (uint256 i = 0; i < recipients.length; i++) {
            uint256 tokenId = _nextTokenId++;
            _safeMint(recipients[i], tokenId);
            emit SeatMinted(tokenId, recipients[i]);
        }
    }

    function revoke(uint256 tokenId) external onlyOwner {
        _requireOwned(tokenId);
        _revoked[tokenId] = true;
        emit SeatRevoked(tokenId);
    }

    function unrevoke(uint256 tokenId) external onlyOwner {
        _requireOwned(tokenId);
        _revoked[tokenId] = false;
        emit SeatUnrevoked(tokenId);
    }

    function setBaseURI(string calldata uri) external onlyOwner {
        _baseTokenURI = uri;
    }

    function isRevoked(uint256 tokenId) external view returns (bool) {
        _requireOwned(tokenId);
        return _revoked[tokenId];
    }

    function isValidSeat(address wallet) external view returns (bool) {
        uint256 balance = balanceOf(wallet);
        for (uint256 i = 0; i < balance; i++) {
            uint256 tokenId = tokenOfOwnerByIndex(wallet, i);
            if (!_revoked[tokenId]) {
                return true;
            }
        }
        return false;
    }

    function tokenURI(uint256 tokenId) public view override returns (string memory) {
        _requireOwned(tokenId);
        string memory base = _baseURI();
        if (bytes(base).length == 0) {
            return "";
        }
        return string(abi.encodePacked(base, Strings.toString(tokenId), ".json"));
    }

    function _baseURI() internal view override returns (string memory) {
        return _baseTokenURI;
    }

    // ERC721Enumerable required overrides
    function _update(address to, uint256 tokenId, address auth)
        internal
        override(ERC721, ERC721Enumerable)
        returns (address)
    {
        address from = _ownerOf(tokenId);
        if (from != address(0) && to != address(0)) {
            revert SeatNonTransferable();
        }
        return super._update(to, tokenId, auth);
    }

    function _increaseBalance(address account, uint128 value)
        internal
        override(ERC721, ERC721Enumerable)
    {
        super._increaseBalance(account, value);
    }

    function supportsInterface(bytes4 interfaceId)
        public
        view
        override(ERC721, ERC721Enumerable)
        returns (bool)
    {
        return super.supportsInterface(interfaceId);
    }
}
