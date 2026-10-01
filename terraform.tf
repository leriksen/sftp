terraform {
  required_version = "~>1.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~>4.0"
    }

    azapi = {
      source  = "Azure/azapi"
      version = "~>2.0"
    }

    time = {
      source  = "hashicorp/time"
      version = "~>0.9"
    }

    # azuredevops = {
    #   source = "microsoft/azuredevops"
    #   version = ">= 0.1.0"
    # }
  }

  # State lives in TFC rather than a local file: a local backend gives state
  # no encryption at rest, no access control and no audit trail (it once held
  # Entra service-principal secrets in cleartext).
  #
  # prefix + TF_WORKSPACE=dev resolves to the "sftp-dev" workspace, matching
  # the sibling adls project's adls-dev. That workspace runs in *remote*
  # execution mode and inherits ARM_* from the org-global "azure" variable set,
  # so plans and applies execute in TFC rather than here. See .terraformignore
  # for what is kept out of the uploaded config bundle -- notably tests/, which
  # carries the Entra service principal secrets.
  backend "remote" {
    organization = "leif-lab3"
    hostname     = "app.terraform.io"

    workspaces {
      prefix = "sftp-"
    }
  }

  #  backend "local" {
  #    path = "./terraform.tfstate"
  #  }
}
