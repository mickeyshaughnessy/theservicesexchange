import { ethers } from "hardhat";

const BASE_URI = "https://mithril-media.sfo3.digitaloceanspaces.com/theservicesexchange/rse-seats/";

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("Deploying RSESeat with account:", deployer.address);

  const RSESeat = await ethers.getContractFactory("RSESeat");
  const contract = await RSESeat.deploy(deployer.address);
  await contract.waitForDeployment();

  const address = await contract.getAddress();
  console.log("RSESeat deployed to:", address);
  console.log("Owner:", deployer.address);

  console.log("Setting baseURI...");
  const tx = await contract.setBaseURI(BASE_URI);
  await tx.wait();
  console.log("baseURI set to:", BASE_URI);
  console.log("Token #1 will resolve to:", BASE_URI + "1.json");
  console.log("");
  console.log("Add to config.py:");
  console.log(`  RSE_SEAT_CONTRACT_ADDRESS = '${address}'`);
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
