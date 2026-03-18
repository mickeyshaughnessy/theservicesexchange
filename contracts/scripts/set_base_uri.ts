import { ethers } from "hardhat";

const CONTRACT_ADDRESS = "0x151fEB62F0D3085617a086130cc67f7f18Ce33CE";
const BASE_URI = "https://mithril-media.sfo3.digitaloceanspaces.com/theservicesexchange/rse-seats/";

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("Caller:", deployer.address);

  const RSESeat = await ethers.getContractAt("RSESeat", CONTRACT_ADDRESS);
  console.log("Calling setBaseURI on", CONTRACT_ADDRESS);

  const tx = await RSESeat.setBaseURI(BASE_URI, {
    maxFeePerGas: ethers.parseUnits("0.1", "gwei"),
    maxPriorityFeePerGas: ethers.parseUnits("0.01", "gwei"),
  });
  console.log("tx hash:", tx.hash);
  await tx.wait();
  console.log("baseURI set to:", BASE_URI);
  console.log("Token #1 resolves to:", BASE_URI + "1.json");
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
