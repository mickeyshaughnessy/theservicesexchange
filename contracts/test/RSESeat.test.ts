import { expect } from "chai";
import { ethers } from "hardhat";
import { RSESeat } from "../typechain-types";
import { HardhatEthersSigner } from "@nomicfoundation/hardhat-ethers/signers";

const BASE_URI = "https://mithril-media.sfo3.digitaloceanspaces.com/theservicesexchange/rse-seats/";

describe("RSESeat", function () {
  let contract: RSESeat;
  let owner: HardhatEthersSigner;
  let addr1: HardhatEthersSigner;
  let addr2: HardhatEthersSigner;
  let addr3: HardhatEthersSigner;

  beforeEach(async function () {
    [owner, addr1, addr2, addr3] = await ethers.getSigners();
    const Factory = await ethers.getContractFactory("RSESeat");
    contract = await Factory.deploy(owner.address);
    await contract.waitForDeployment();
  });

  // ── Deployment ──────────────────────────────────────────────────────────────

  describe("Deployment", function () {
    it("has correct name and symbol", async function () {
      expect(await contract.name()).to.equal("RSE Seat");
      expect(await contract.symbol()).to.equal("RSESEAT");
    });

    it("sets deployer as owner", async function () {
      expect(await contract.owner()).to.equal(owner.address);
    });

    it("starts with totalSupply of 0", async function () {
      expect(await contract.totalSupply()).to.equal(0n);
    });
  });

  // ── mint ─────────────────────────────────────────────────────────────────────

  describe("mint", function () {
    it("assigns sequential IDs starting at 1", async function () {
      await contract.mint(addr1.address);
      await contract.mint(addr2.address);
      await contract.mint(addr3.address);
      expect(await contract.ownerOf(1)).to.equal(addr1.address);
      expect(await contract.ownerOf(2)).to.equal(addr2.address);
      expect(await contract.ownerOf(3)).to.equal(addr3.address);
    });

    it("returns the minted tokenId", async function () {
      const tokenId = await contract.mint.staticCall(addr1.address);
      expect(tokenId).to.equal(1n);
    });

    it("emits SeatMinted", async function () {
      await expect(contract.mint(addr1.address))
        .to.emit(contract, "SeatMinted")
        .withArgs(1n, addr1.address);
    });

    it("increments totalSupply", async function () {
      await contract.mint(addr1.address);
      await contract.mint(addr2.address);
      expect(await contract.totalSupply()).to.equal(2n);
    });

    it("reverts for non-owner", async function () {
      await expect(contract.connect(addr1).mint(addr2.address))
        .to.be.revertedWithCustomError(contract, "OwnableUnauthorizedAccount");
    });
  });

  // ── mintBatch ────────────────────────────────────────────────────────────────

  describe("mintBatch", function () {
    it("mints one seat to each recipient in order", async function () {
      await contract.mintBatch([addr1.address, addr2.address, addr3.address]);
      expect(await contract.ownerOf(1)).to.equal(addr1.address);
      expect(await contract.ownerOf(2)).to.equal(addr2.address);
      expect(await contract.ownerOf(3)).to.equal(addr3.address);
    });

    it("emits SeatMinted for each recipient", async function () {
      await expect(contract.mintBatch([addr1.address, addr2.address]))
        .to.emit(contract, "SeatMinted").withArgs(1n, addr1.address)
        .and.to.emit(contract, "SeatMinted").withArgs(2n, addr2.address);
    });

    it("updates totalSupply correctly", async function () {
      await contract.mintBatch([addr1.address, addr2.address, addr3.address]);
      expect(await contract.totalSupply()).to.equal(3n);
    });

    it("reverts for non-owner", async function () {
      await expect(contract.connect(addr1).mintBatch([addr2.address]))
        .to.be.revertedWithCustomError(contract, "OwnableUnauthorizedAccount");
    });

    it("IDs continue correctly after a prior mint", async function () {
      await contract.mint(addr1.address); // tokenId 1
      await contract.mintBatch([addr2.address, addr3.address]); // tokenIds 2, 3
      expect(await contract.ownerOf(2)).to.equal(addr2.address);
      expect(await contract.ownerOf(3)).to.equal(addr3.address);
    });
  });

  // ── revoke / unrevoke ────────────────────────────────────────────────────────

  describe("revoke", function () {
    beforeEach(async function () {
      await contract.mint(addr1.address);
    });

    it("marks a token as revoked", async function () {
      await contract.revoke(1);
      expect(await contract.isRevoked(1)).to.equal(true);
    });

    it("emits SeatRevoked", async function () {
      await expect(contract.revoke(1))
        .to.emit(contract, "SeatRevoked")
        .withArgs(1n);
    });

    it("reverts for non-owner", async function () {
      await expect(contract.connect(addr1).revoke(1))
        .to.be.revertedWithCustomError(contract, "OwnableUnauthorizedAccount");
    });

    it("reverts for non-existent token", async function () {
      await expect(contract.revoke(999))
        .to.be.revertedWithCustomError(contract, "ERC721NonexistentToken");
    });
  });

  describe("unrevoke", function () {
    beforeEach(async function () {
      await contract.mint(addr1.address);
      await contract.revoke(1);
    });

    it("clears the revocation flag", async function () {
      await contract.unrevoke(1);
      expect(await contract.isRevoked(1)).to.equal(false);
    });

    it("emits SeatUnrevoked", async function () {
      await expect(contract.unrevoke(1))
        .to.emit(contract, "SeatUnrevoked")
        .withArgs(1n);
    });

    it("reverts for non-owner", async function () {
      await expect(contract.connect(addr1).unrevoke(1))
        .to.be.revertedWithCustomError(contract, "OwnableUnauthorizedAccount");
    });
  });

  describe("isRevoked", function () {
    it("returns false for a freshly minted token", async function () {
      await contract.mint(addr1.address);
      expect(await contract.isRevoked(1)).to.equal(false);
    });

    it("reverts for non-existent token", async function () {
      await expect(contract.isRevoked(999))
        .to.be.revertedWithCustomError(contract, "ERC721NonexistentToken");
    });
  });

  // ── isValidSeat ──────────────────────────────────────────────────────────────

  describe("isValidSeat", function () {
    it("returns false for address with no seats", async function () {
      expect(await contract.isValidSeat(addr1.address)).to.equal(false);
    });

    it("returns true for holder of unrevoked seat", async function () {
      await contract.mint(addr1.address);
      expect(await contract.isValidSeat(addr1.address)).to.equal(true);
    });

    it("returns false for holder of revoked seat", async function () {
      await contract.mint(addr1.address);
      await contract.revoke(1);
      expect(await contract.isValidSeat(addr1.address)).to.equal(false);
    });

    it("returns true when at least one of multiple seats is unrevoked", async function () {
      await contract.mintBatch([addr1.address, addr1.address]);
      await contract.revoke(1);
      expect(await contract.isValidSeat(addr1.address)).to.equal(true);
    });

    it("returns false when all seats are revoked", async function () {
      await contract.mintBatch([addr1.address, addr1.address]);
      await contract.revoke(1);
      await contract.revoke(2);
      expect(await contract.isValidSeat(addr1.address)).to.equal(false);
    });

    it("returns true again after unrevoke", async function () {
      await contract.mint(addr1.address);
      await contract.revoke(1);
      await contract.unrevoke(1);
      expect(await contract.isValidSeat(addr1.address)).to.equal(true);
    });
  });

  // ── Transfers (soulbound — all transfers revert) ─────────────────────────────

  describe("Transfers", function () {
    beforeEach(async function () {
      await contract.mint(addr1.address);
    });

    it("reverts transferFrom with SeatNonTransferable", async function () {
      await expect(
        contract.connect(addr1).transferFrom(addr1.address, addr2.address, 1)
      ).to.be.revertedWithCustomError(contract, "SeatNonTransferable");
    });

    it("reverts safeTransferFrom with SeatNonTransferable", async function () {
      await expect(
        contract.connect(addr1)["safeTransferFrom(address,address,uint256)"](
          addr1.address, addr2.address, 1
        )
      ).to.be.revertedWithCustomError(contract, "SeatNonTransferable");
    });

    it("original holder retains ownership after failed transfer", async function () {
      await expect(
        contract.connect(addr1).transferFrom(addr1.address, addr2.address, 1)
      ).to.be.revertedWithCustomError(contract, "SeatNonTransferable");
      expect(await contract.ownerOf(1)).to.equal(addr1.address);
      expect(await contract.isValidSeat(addr1.address)).to.equal(true);
      expect(await contract.isValidSeat(addr2.address)).to.equal(false);
    });

    it("revoked seat transfer also reverts", async function () {
      await contract.revoke(1);
      await expect(
        contract.connect(addr1).transferFrom(addr1.address, addr2.address, 1)
      ).to.be.revertedWithCustomError(contract, "SeatNonTransferable");
    });
  });

  // ── tokenURI / baseURI ───────────────────────────────────────────────────────

  describe("tokenURI", function () {
    it("returns empty string when no baseURI is set", async function () {
      await contract.mint(addr1.address);
      expect(await contract.tokenURI(1)).to.equal("");
    });

    it("returns baseURI + tokenId + .json when baseURI is set", async function () {
      await contract.setBaseURI(BASE_URI);
      await contract.mint(addr1.address);
      expect(await contract.tokenURI(1)).to.equal(BASE_URI + "1.json");
    });

    it("works correctly for token IDs > 9", async function () {
      await contract.setBaseURI(BASE_URI);
      for (let i = 0; i < 10; i++) await contract.mint(addr1.address);
      expect(await contract.tokenURI(10)).to.equal(BASE_URI + "10.json");
    });

    it("reverts for non-existent token", async function () {
      await expect(contract.tokenURI(999))
        .to.be.revertedWithCustomError(contract, "ERC721NonexistentToken");
    });

    it("setBaseURI reverts for non-owner", async function () {
      await expect(contract.connect(addr1).setBaseURI(BASE_URI))
        .to.be.revertedWithCustomError(contract, "OwnableUnauthorizedAccount");
    });
  });

  // ── ERC-165 interface support ────────────────────────────────────────────────

  describe("supportsInterface", function () {
    it("supports ERC-721 (0x80ac58cd)", async function () {
      expect(await contract.supportsInterface("0x80ac58cd")).to.equal(true);
    });

    it("supports ERC-721Enumerable (0x780e9d63)", async function () {
      expect(await contract.supportsInterface("0x780e9d63")).to.equal(true);
    });

    it("does not support a random interface", async function () {
      expect(await contract.supportsInterface("0xdeadbeef")).to.equal(false);
    });
  });
});
