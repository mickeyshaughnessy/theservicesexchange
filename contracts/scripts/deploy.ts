import { ethers } from "hardhat";

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("Deploying RSESeat with account:", deployer.address);

  const RSESeat = await ethers.getContractFactory("RSESeat");
  const contract = await RSESeat.deploy(deployer.address);
  await contract.waitForDeployment();

  const address = await contract.getAddress();
  console.log("RSESeat deployed to:", address);
  console.log("Owner:", deployer.address);
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
